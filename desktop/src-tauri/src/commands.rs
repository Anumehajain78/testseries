//! Everything the two local pages are allowed to ask for, plus the one thing
//! the remote candidate interface is allowed to ask for.

use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use uuid::Uuid;

use crate::windows;
use crate::AppState;
use exam_lab_core::api::Api;
use exam_lab_core::config::{self, Enrolment};

/// Roles that may release a locked workstation. A candidate's own credentials
/// authenticate perfectly well against `/auth/login` — the role is what stops
/// them letting themselves out.
const MAY_RELEASE: [&str; 2] = ["ADMIN", "FACULTY"];

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SetupState {
    pub enrolled: bool,
    pub api_base_url: String,
    pub candidate_url: String,
    pub machine_id: String,
    /// Offered as the default, because on a properly imaged lab the hostname
    /// is already the machine identifier on the floor plan.
    pub hostname: String,
    /// Why the setup screen is being shown again, when it is not a first run.
    pub notice: Option<String>,
}

#[tauri::command]
pub fn setup_state(state: State<'_, AppState>) -> SetupState {
    let enrolment = state.enrolment.lock().expect("enrolment lock poisoned");
    let hostname = config::local_hostname().unwrap_or_default();
    match enrolment.as_ref() {
        Some(existing) => SetupState {
            enrolled: true,
            api_base_url: existing.api_base_url.clone(),
            candidate_url: existing.candidate_url.clone(),
            machine_id: existing.machine_id.clone(),
            hostname,
            notice: state.notice.lock().expect("notice lock poisoned").clone(),
        },
        None => SetupState {
            enrolled: false,
            api_base_url: String::new(),
            candidate_url: String::new(),
            machine_id: hostname.clone(),
            hostname,
            notice: state.notice.lock().expect("notice lock poisoned").clone(),
        },
    }
}

/// First run: exchange the token an administrator typed for this machine's own
/// secret, write it down, and go straight into the examination window.
#[tauri::command]
pub async fn enrol(
    app: AppHandle,
    state: State<'_, AppState>,
    api_base_url: String,
    candidate_url: String,
    enrolment_token: String,
    machine_id: String,
    hostname: String,
) -> Result<(), String> {
    let api_base_url = api_base_url.trim().trim_end_matches('/').to_string();
    let candidate_url = candidate_url.trim().trim_end_matches('/').to_string();
    let machine_id = machine_id.trim().to_string();
    let hostname = hostname.trim().to_string();

    if api_base_url.is_empty() || candidate_url.is_empty() || machine_id.is_empty() {
        return Err("The server addresses and the machine identifier are all required.".into());
    }
    // Caught here rather than at the first request, because "nothing happened"
    // is a much worse thing to hand an administrator standing at a workstation
    // than "that is not an address".
    if url::Url::parse(&api_base_url).is_err() || url::Url::parse(&candidate_url).is_err() {
        return Err("Those addresses are not valid URLs. Include http:// or https://.".into());
    }

    let api = Api::new(&api_base_url).map_err(|error| error.to_string())?;
    let credential = api
        .enrol(
            enrolment_token.trim(),
            &machine_id,
            if hostname.is_empty() {
                None
            } else {
                Some(&hostname)
            },
        )
        .await
        .map_err(|error| error.to_string())?;

    let enrolment = Enrolment {
        api_base_url,
        candidate_url,
        machine_id: credential.machine_id,
        hostname: (!hostname.is_empty()).then_some(hostname),
        secret: credential.secret,
    };

    // Written before the window opens. If persisting fails — a read-only
    // profile, a full disk — the administrator has to know now, while they are
    // still standing there, rather than discovering at the next boot that the
    // secret they can never retrieve again was never saved.
    config::save(&state.store_dir, &enrolment).map_err(|error| {
        format!(
            "Enrolled, but could not save the credential to {}: {error}",
            state.store_dir.display()
        )
    })?;

    *state.enrolment.lock().expect("enrolment lock poisoned") = Some(enrolment.clone());
    *state.notice.lock().expect("notice lock poisoned") = None;

    windows::start_examination(&app, &enrolment).map_err(|error| error.to_string())?;
    if let Some(setup) = app.get_webview_window("setup") {
        let _ = setup.close();
    }
    Ok(())
}

/// Called by the candidate interface over IPC. See the long note on
/// `LabClient::bind_session` — without this the server has no session to file
/// an invigilation event against, and nothing else in the API supplies one.
#[tauri::command]
pub fn bind_session(state: State<'_, AppState>, session_id: String) -> Result<(), String> {
    let session_id = Uuid::parse_str(session_id.trim())
        .map_err(|_| format!("{session_id:?} is not a session identifier"))?;
    let client = state.client.lock().expect("client lock poisoned").clone();
    match client {
        Some(client) => {
            client.bind_session(session_id);
            Ok(())
        }
        // Reachable in exactly one case: the page loaded before enrolment
        // finished. Not an error worth showing anyone — the script retries.
        None => Err("This workstation is not reporting yet.".into()),
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Released {
    pub full_name: String,
}

/// Let an invigilator out of the locked window.
///
/// There is no endpoint that answers "may this person release this
/// workstation", so this asks the question the contract does answer — are these
/// credentials real, and is the holder staff — and decides here. That means the
/// check is only as good as the machine it runs on: somebody who can patch the
/// binary can skip it. It is a convenience for the person with the keys, not a
/// security boundary.
#[tauri::command]
pub async fn unlock(
    app: AppHandle,
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<Released, String> {
    let api_base_url = {
        let enrolment = state.enrolment.lock().expect("enrolment lock poisoned");
        match enrolment.as_ref() {
            Some(existing) => existing.api_base_url.clone(),
            None => return Err("This workstation is not enrolled.".into()),
        }
    };

    let api = Api::new(&api_base_url).map_err(|error| error.to_string())?;
    let staff = api
        .staff_login(email.trim(), &password)
        .await
        .map_err(|error| error.to_string())?;

    if !MAY_RELEASE.contains(&staff.role.as_str()) {
        return Err("Only an invigilator or administrator can release this workstation.".into());
    }

    let client = state.client.lock().expect("client lock poisoned").clone();
    let who = staff.full_name.clone();
    let handle = app.clone();
    // Deferred so this command's reply reaches the prompt before the process
    // goes away; an invigilator who sees nothing happen types their password
    // again.
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        match client {
            Some(client) => crate::lockdown::release(&handle, client, &who).await,
            None => handle.exit(0),
        }
    });

    Ok(Released {
        full_name: staff.full_name,
    })
}

/// The invigilator changed their mind. Hand the screen back to the candidate.
#[tauri::command]
pub fn dismiss_unlock(app: AppHandle, state: State<'_, AppState>) {
    if let Some(window) = app.get_webview_window("unlock") {
        let _ = window.close();
    }
    state.lockdown.end_unlock();
    if let Some(exam) = app.get_webview_window("exam") {
        let _ = exam.set_always_on_top(true);
        let _ = exam.set_focus();
    }
}
