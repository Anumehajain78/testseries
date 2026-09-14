//! The examination server, as this client sees it.
//!
//! Only five calls, and every one of them exists in `backend/openapi.json`.
//! Nothing here invents an endpoint: where the desktop client wants something
//! the contract does not offer (see `bind_session` in `client.rs`), that is
//! recorded as a gap rather than papered over with a guessed URL.

use std::time::Duration;

use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde_json::json;
use uuid::Uuid;

/// Short, because every call this client makes is on a LAN and sits on the
/// critical path of either starting an examination or proving a machine is
/// still alive. Waiting thirty seconds for a dead server only delays the
/// retry that was going to happen anyway.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(8);

#[derive(Debug)]
pub enum ApiError {
    /// The server could not be reached at all — cable out, wrong address, or
    /// the API process is down. Distinguished from a refusal because the two
    /// call for opposite responses: retry one, stop and ask a human about the
    /// other.
    Unreachable(String),
    Refused { status: u16, detail: String },
    Malformed(String),
}

impl ApiError {
    pub fn is_unauthorized(&self) -> bool {
        matches!(self, ApiError::Refused { status: 401, .. })
    }

    pub fn is_unreachable(&self) -> bool {
        matches!(self, ApiError::Unreachable(_))
    }
}

impl std::fmt::Display for ApiError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ApiError::Unreachable(why) => write!(f, "Cannot reach the examination server ({why})"),
            ApiError::Refused { status, detail } => write!(f, "{detail} (HTTP {status})"),
            ApiError::Malformed(why) => write!(f, "The server replied with something unexpected ({why})"),
        }
    }
}

impl std::error::Error for ApiError {}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MachineCredential {
    pub machine_id: String,
    pub secret: String,
    #[allow(dead_code)]
    pub lab_id: Uuid,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MachineToken {
    pub access_token: String,
    pub expires_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TokenPair {
    user: UserOut,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UserOut {
    full_name: String,
    role: String,
}

/// Who signed in at the unlock prompt, and whether they are allowed to.
#[derive(Debug, Clone)]
pub struct Staff {
    pub full_name: String,
    pub role: String,
}

pub struct Api {
    base: String,
    http: reqwest::Client,
}

impl Api {
    pub fn new(base_url: &str) -> Result<Self, ApiError> {
        let http = reqwest::Client::builder()
            .timeout(REQUEST_TIMEOUT)
            .build()
            .map_err(|error| ApiError::Unreachable(error.to_string()))?;
        Ok(Self {
            base: base_url.trim_end_matches('/').to_string(),
            http,
        })
    }

    async fn post(
        &self,
        path: &str,
        body: serde_json::Value,
        token: Option<&str>,
    ) -> Result<String, ApiError> {
        let mut request = self.http.post(format!("{}{path}", self.base)).json(&body);
        if let Some(token) = token {
            request = request.bearer_auth(token);
        }

        let response = request
            .send()
            .await
            .map_err(|error| ApiError::Unreachable(error.to_string()))?;

        let status = response.status();
        let text = response.text().await.unwrap_or_default();
        if status.is_success() {
            return Ok(text);
        }
        Err(ApiError::Refused {
            status: status.as_u16(),
            detail: explain(&text, status.as_u16()),
        })
    }

    /// Stage one of enrolment: trade the token an administrator typed for a
    /// secret that belongs to this machine alone.
    pub async fn enrol(
        &self,
        enrolment_token: &str,
        machine_id: &str,
        hostname: Option<&str>,
    ) -> Result<MachineCredential, ApiError> {
        let body = self
            .post(
                "/auth/machine/enrol",
                json!({
                    "enrolmentToken": enrolment_token,
                    "machineId": machine_id,
                    "hostname": hostname,
                }),
                None,
            )
            .await?;
        decode(&body)
    }

    /// Stage two, and every run afterwards: the secret buys a short-lived token.
    pub async fn machine_token(
        &self,
        machine_id: &str,
        secret: &str,
    ) -> Result<MachineToken, ApiError> {
        let body = self
            .post(
                "/auth/machine/token",
                json!({ "machineId": machine_id, "secret": secret }),
                None,
            )
            .await?;
        decode(&body)
    }

    /// `session_id` is optional in the contract, and when present the server
    /// also stamps the candidate's session — which is what turns the monitor's
    /// connection column green rather than only the floor plan's.
    pub async fn heartbeat(
        &self,
        token: &str,
        machine_id: &str,
        session_id: Option<Uuid>,
    ) -> Result<(), ApiError> {
        self.post(
            &format!("/computers/{machine_id}/heartbeat"),
            json!({
                "machineId": machine_id,
                "sessionId": session_id,
                "occurredAt": Utc::now().to_rfc3339(),
            }),
            Some(token),
        )
        .await
        .map(drop)
    }

    /// `event` must be one of `app.services.machines.REPORTABLE`; anything else
    /// is refused with a 422 rather than stored, so the caller uses the
    /// constants in `lockdown.rs` instead of free text.
    pub async fn report_event(
        &self,
        token: &str,
        session_id: Uuid,
        event: &str,
        occurred_at: DateTime<Utc>,
        detail: Option<&str>,
    ) -> Result<(), ApiError> {
        self.post(
            &format!("/sessions/{session_id}/events"),
            json!({
                "event": event,
                // What this machine believes, sent as-is. The server records
                // its own arrival time beside it, so a workstation with a
                // wrong clock shows up in the data instead of quietly
                // reordering somebody's timeline.
                "occurredAt": occurred_at.to_rfc3339(),
                "detail": detail,
            }),
            Some(token),
        )
        .await
        .map(drop)
    }

    /// Used only by the unlock prompt. There is no endpoint that asks "may this
    /// person release a workstation", so the client asks the nearest question
    /// the contract does answer — can these credentials sign in, and are they
    /// staff — and decides locally. A candidate's own credentials will
    /// authenticate successfully here and still be refused, because the role
    /// check happens after.
    pub async fn staff_login(&self, email: &str, password: &str) -> Result<Staff, ApiError> {
        let body = self
            .post(
                "/auth/login",
                json!({ "email": email, "password": password }),
                None,
            )
            .await?;
        let pair: TokenPair = decode(&body)?;
        Ok(Staff {
            full_name: pair.user.full_name,
            role: pair.user.role,
        })
    }
}

fn decode<T: serde::de::DeserializeOwned>(body: &str) -> Result<T, ApiError> {
    serde_json::from_str(body).map_err(|error| ApiError::Malformed(error.to_string()))
}

/// FastAPI puts a plain string in `detail` for the errors this client can
/// provoke, and a list of field errors for a 422. Neither shape is worth a
/// struct; an administrator standing at a workstation needs a sentence.
fn explain(body: &str, status: u16) -> String {
    match serde_json::from_str::<serde_json::Value>(body) {
        Ok(value) => match value.get("detail") {
            Some(serde_json::Value::String(message)) => message.clone(),
            Some(other) => other.to_string(),
            None => fallback(status),
        },
        Err(_) if body.trim().is_empty() => fallback(status),
        Err(_) => body.chars().take(300).collect(),
    }
}

fn fallback(status: u16) -> String {
    match status {
        401 => "The server rejected this machine's credentials".to_string(),
        403 => "This machine is not allowed to do that".to_string(),
        404 => "The server does not know about that".to_string(),
        _ => format!("The server refused the request (HTTP {status})"),
    }
}
