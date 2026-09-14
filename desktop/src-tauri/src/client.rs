//! The reporting half of the workstation: a token it keeps fresh, a heartbeat
//! it does not stop sending, and the invigilation signals it owes the server.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use chrono::{DateTime, Duration as ChronoDuration, Utc};
use tokio::sync::Mutex as AsyncMutex;
use uuid::Uuid;

use crate::api::{Api, ApiError};
use crate::config::Enrolment;
use crate::lockdown::events;

/// `EXAM_HEARTBEAT_INTERVAL_SECONDS` in `backend/.env.example`. The server
/// calls a machine 'warning' at 30s and 'offline' at 90s, so this leaves room
/// for two missed beats before an invigilator sees anything — which is the
/// point: a single dropped packet is not news.
const HEARTBEAT_SECONDS: u64 = 10;

/// Renew this far ahead of expiry. Wide enough that a beat never lands on an
/// already-dead token because of clock skew between machine and server.
const RENEW_MARGIN_SECONDS: i64 = 60;

/// How many invigilation signals to hold while no session is bound.
///
/// There is a real gap behind this number: see [`LabClient::bind_session`]. A
/// candidate who alt-tabs twenty times before their client identifies its
/// session should still have all twenty on the record, but an unbounded queue
/// on a machine nobody ever sits at is a slow leak, so it stops at a number
/// far past anything a genuine sitting produces.
const PENDING_LIMIT: usize = 256;

struct CachedToken {
    value: String,
    expires_at: DateTime<Utc>,
}

struct PendingEvent {
    event: &'static str,
    occurred_at: DateTime<Utc>,
    detail: Option<String>,
}

pub struct LabClient {
    api: Api,
    machine_id: String,
    secret: String,
    candidate_url: String,
    token: AsyncMutex<Option<CachedToken>>,
    session: Mutex<Option<Uuid>>,
    pending: Mutex<VecDeque<PendingEvent>>,
    /// Tracks whether the last beat landed, so the recovery from an outage can
    /// be reported once rather than the outage being inferred from silence on
    /// both ends. `CONNECTION_LOST` is deliberately never sent: the server
    /// derives it from the absence of heartbeats, and a client that is offline
    /// cannot tell anyone it is offline.
    reachable: AtomicBool,
}

impl LabClient {
    pub fn new(enrolment: &Enrolment) -> Result<Self, ApiError> {
        Ok(Self {
            api: Api::new(&enrolment.api_base_url)?,
            machine_id: enrolment.machine_id.clone(),
            secret: enrolment.secret.clone(),
            candidate_url: enrolment.candidate_url.trim_end_matches('/').to_string(),
            token: AsyncMutex::new(None),
            session: Mutex::new(None),
            pending: Mutex::new(VecDeque::new()),
            reachable: AtomicBool::new(true),
        })
    }

    pub fn candidate_url(&self) -> &str {
        &self.candidate_url
    }

    pub fn session(&self) -> Option<Uuid> {
        *self.session.lock().expect("session lock poisoned")
    }

    /// Attach this workstation to the candidate session sitting at it.
    ///
    /// **This is the one thing the server API cannot tell us.**
    /// `POST /sessions/{id}/events` needs a session UUID, and there is no
    /// endpoint that maps a machine to the session currently checked in on it —
    /// `GET /me/sessions` needs a candidate token, which a machine subject is
    /// refused. So the candidate interface has to say so, over IPC, and until
    /// it does every focus event is held in the queue above rather than sent.
    /// Heartbeats are unaffected; they carry the session only as an optional
    /// extra.
    pub fn bind_session(self: &Arc<Self>, session_id: Uuid) {
        let changed = {
            let mut guard = self.session.lock().expect("session lock poisoned");
            let changed = *guard != Some(session_id);
            *guard = Some(session_id);
            changed
        };
        if changed {
            log::info!("bound to session {session_id}");
            let client = Arc::clone(self);
            tauri::async_runtime::spawn(async move { client.flush_pending().await });
        }
    }

    async fn token(&self) -> Result<String, ApiError> {
        let mut guard = self.token.lock().await;
        if let Some(cached) = guard.as_ref() {
            if cached.expires_at - Utc::now() > ChronoDuration::seconds(RENEW_MARGIN_SECONDS) {
                return Ok(cached.value.clone());
            }
        }

        let fresh = self.api.machine_token(&self.machine_id, &self.secret).await?;
        let value = fresh.access_token.clone();
        *guard = Some(CachedToken {
            value: fresh.access_token,
            expires_at: fresh.expires_at,
        });
        Ok(value)
    }

    async fn discard_token(&self) {
        *self.token.lock().await = None;
    }

    pub async fn heartbeat(&self) -> Result<(), ApiError> {
        let session = self.session();
        let token = self.token().await?;
        match self.api.heartbeat(&token, &self.machine_id, session).await {
            // The expiry we compared against was measured by this machine's
            // clock. When the server disagrees, the server is right — take a
            // fresh token and beat again rather than dropping a beat and
            // showing up as a warning on the monitor.
            Err(error) if error.is_unauthorized() => {
                self.discard_token().await;
                let token = self.token().await?;
                self.api.heartbeat(&token, &self.machine_id, session).await
            }
            other => other,
        }
    }

    /// Report a signal, holding it if no session is bound yet.
    pub async fn report(&self, event: &'static str, detail: Option<String>) {
        let occurred_at = Utc::now();
        let Some(session_id) = self.session() else {
            self.enqueue(PendingEvent {
                event,
                occurred_at,
                detail,
            });
            return;
        };
        self.send(session_id, event, occurred_at, detail.as_deref())
            .await;
    }

    /// Report a signal that is only meaningful while somebody is sitting there.
    /// Dropped rather than queued when no session is bound — a connection
    /// blip on an idle machine is not part of anyone's examination record.
    async fn report_now(&self, event: &'static str, detail: Option<&str>) {
        if let Some(session_id) = self.session() {
            self.send(session_id, event, Utc::now(), detail).await;
        }
    }

    async fn send(
        &self,
        session_id: Uuid,
        event: &'static str,
        occurred_at: DateTime<Utc>,
        detail: Option<&str>,
    ) {
        let outcome = self.send_once(session_id, event, occurred_at, detail).await;
        match outcome {
            Ok(()) => log::info!("reported {event}"),
            Err(error) if error.is_unreachable() => {
                // Re-queue: an outage during an examination is exactly when
                // the record matters most, and the heartbeat loop will notice
                // the server again within ten seconds.
                log::warn!("holding {event} until the server is reachable: {error}");
                self.enqueue(PendingEvent {
                    event,
                    occurred_at,
                    detail: detail.map(str::to_string),
                });
            }
            Err(error) => log::error!("{event} refused and discarded: {error}"),
        }
    }

    async fn send_once(
        &self,
        session_id: Uuid,
        event: &str,
        occurred_at: DateTime<Utc>,
        detail: Option<&str>,
    ) -> Result<(), ApiError> {
        let token = self.token().await?;
        match self
            .api
            .report_event(&token, session_id, event, occurred_at, detail)
            .await
        {
            Err(error) if error.is_unauthorized() => {
                self.discard_token().await;
                let token = self.token().await?;
                self.api
                    .report_event(&token, session_id, event, occurred_at, detail)
                    .await
            }
            other => other,
        }
    }

    fn enqueue(&self, event: PendingEvent) {
        let mut queue = self.pending.lock().expect("pending lock poisoned");
        if queue.len() >= PENDING_LIMIT {
            // Drop the oldest. The recent signals are the ones an invigilator
            // is about to be asked about.
            queue.pop_front();
        }
        queue.push_back(event);
    }

    async fn flush_pending(&self) {
        let Some(session_id) = self.session() else {
            return;
        };
        loop {
            let next = {
                let mut queue = self.pending.lock().expect("pending lock poisoned");
                queue.pop_front()
            };
            let Some(event) = next else { return };

            // Bound to a local first: the borrow of `event.detail` has to end
            // before the failure path can move `event` back into the queue.
            let outcome = self
                .send_once(session_id, event.event, event.occurred_at, event.detail.as_deref())
                .await;

            if let Err(error) = outcome {
                if error.is_unreachable() {
                    // Put it back at the head so the order the candidate
                    // actually produced survives the outage, and stop: the
                    // rest of the queue will fail the same way.
                    let mut queue = self.pending.lock().expect("pending lock poisoned");
                    queue.push_front(event);
                    return;
                }
                log::error!("{} refused and discarded: {error}", event.event);
            }
        }
    }
}

/// Beats until the process ends. Never returns, and never gives up: a
/// workstation that stops reporting is indistinguishable, on the monitor, from
/// one that was switched off, and an invigilator will be sent to look at it.
pub async fn run_heartbeats(client: Arc<LabClient>) {
    let mut ticker = tokio::time::interval(std::time::Duration::from_secs(HEARTBEAT_SECONDS));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

    loop {
        ticker.tick().await;
        match client.heartbeat().await {
            Ok(()) => {
                if !client.reachable.swap(true, Ordering::SeqCst) {
                    log::info!("server reachable again");
                    client
                        .report_now(events::CONNECTION_RESTORED, Some("Heartbeat resumed."))
                        .await;
                }
            }
            Err(error) => {
                if client.reachable.swap(false, Ordering::SeqCst) {
                    log::warn!("heartbeat failing: {error}");
                }
                // Deliberately no backoff. The interval is already long enough
                // to be cheap, and a client that backs off during an outage is
                // a client that comes back late — after the candidate has been
                // marked offline and somebody has walked over.
            }
        }
    }
}

/// Best effort, on the way out.
///
/// Capped rather than awaited to completion: the process is about to exit, and
/// a server that has stopped answering must not turn shutting down into
/// hanging with a fullscreen window still covering the screen.
pub async fn report_closing(client: Arc<LabClient>, detail: String) {
    let _ = tokio::time::timeout(
        std::time::Duration::from_secs(3),
        client.report(events::EXAM_CLIENT_CLOSED, Some(detail)),
    )
    .await;
}
