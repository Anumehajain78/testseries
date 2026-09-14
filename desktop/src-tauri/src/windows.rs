//! The three windows this application ever shows, and the order they happen in.
//!
//! Setup is local and ordinary. The examination window is remote and locked.
//! The unlock prompt is local, and is the only thing allowed to sit above the
//! examination window.

use std::sync::Arc;

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

use crate::client::{run_heartbeats, LabClient};
use crate::config::{self, Enrolment};
use crate::lockdown::{self, GUARD_SCRIPT};
use crate::AppState;

/// Where the candidate interface starts. `/student` is the portal page, which
/// redirects into the live paper on its own — this client deliberately does not
/// try to deep-link to an examination, because it has no way to know which one
/// the person sitting down is enrolled in.
const CANDIDATE_ENTRY: &str = "/student";

pub fn open_setup(app: &AppHandle, notice: Option<String>) -> tauri::Result<WebviewWindow> {
    *app.state::<AppState>()
        .notice
        .lock()
        .expect("notice lock poisoned") = notice;

    if let Some(existing) = app.get_webview_window("setup") {
        let _ = existing.set_focus();
        return Ok(existing);
    }

    WebviewWindowBuilder::new(app, "setup", WebviewUrl::App("setup.html".into()))
        .title("Examination workstation setup")
        .inner_size(760.0, 800.0)
        .min_inner_size(640.0, 640.0)
        .center()
        .build()
}

/// Bring the workstation up: start reporting, then show the paper.
pub fn start_examination(app: &AppHandle, enrolment: &Enrolment) -> Result<(), String> {
    let state = app.state::<AppState>();
    let client = Arc::new(LabClient::new(enrolment).map_err(|error| error.to_string())?);
    *state.client.lock().expect("client lock poisoned") = Some(Arc::clone(&client));

    let landing = format!("{}{CANDIDATE_ENTRY}", client.candidate_url());
    let url = url::Url::parse(&landing)
        .map_err(|error| format!("{landing} is not a usable address: {error}"))?;

    let window = WebviewWindowBuilder::new(app, "exam", WebviewUrl::External(url))
        .title("Examination")
        .fullscreen(true)
        .always_on_top(true)
        // No title bar means no close, minimise or move affordance, and no
        // place for the candidate to read the URL — which would otherwise tell
        // them exactly which host to open in a normal browser beside this one.
        .decorations(false)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .closable(false)
        // Keeps the window out of the taskbar and the alt-tab list on Windows
        // and most Linux desktops. It does not remove it from every switcher,
        // and it does nothing at all on macOS.
        .skip_taskbar(true)
        .focused(true)
        .initialization_script(GUARD_SCRIPT)
        .build()
        .map_err(|error| format!("Could not open the examination window: {error}"))?;

    lockdown::attach(&window, Arc::clone(&client), Arc::clone(&state.lockdown));

    let handle = app.clone();
    let lock = Arc::clone(&state.lockdown);
    tauri::async_runtime::spawn(async move {
        // One beat before the loop starts, purely to find out whether the
        // stored secret is still good. A machine whose record was removed or
        // re-enrolled elsewhere would otherwise sit in front of a candidate
        // looking perfectly normal while reporting nothing at all.
        if let Err(error) = client.heartbeat().await {
            if error.is_unauthorized() {
                log::error!("stored credential rejected: {error}");
                let store = handle.state::<AppState>().store_dir.clone();
                let _ = config::forget(&store);
                *handle
                    .state::<AppState>()
                    .enrolment
                    .lock()
                    .expect("enrolment lock poisoned") = None;
                if let Some(exam) = handle.get_webview_window("exam") {
                    lock.begin_unlock();
                    let _ = exam.close();
                    lock.end_unlock();
                }
                let _ = open_setup(
                    &handle,
                    Some(
                        "The server no longer recognises this workstation's credential. \
                         Enrol it again with a fresh laboratory token."
                            .into(),
                    ),
                );
                return;
            }
            // Anything else — the server is down, the cable is out — is not a
            // reason to refuse to start. The loop retries every ten seconds
            // and the monitor shows the machine as offline until it succeeds.
            log::warn!("first heartbeat failed: {error}");
        }

        run_heartbeats(client).await;
    });

    tauri::async_runtime::spawn(lockdown::hold_window(window, Arc::clone(&state.lockdown)));
    Ok(())
}

/// The invigilator's way out, opened by the global shortcut.
pub fn open_unlock(app: &AppHandle) {
    let state = app.state::<AppState>();
    if lockdown::exam_window(app).is_none() {
        // Nothing is locked, so there is nothing to be let out of.
        return;
    }
    if app.get_webview_window("unlock").is_some() {
        return;
    }

    // Set before the window exists, so the focus change that opening it causes
    // is not filed as the candidate leaving the paper.
    state.lockdown.begin_unlock();

    let built = WebviewWindowBuilder::new(app, "unlock", WebviewUrl::App("unlock.html".into()))
        .title("Release workstation")
        .inner_size(520.0, 460.0)
        .resizable(false)
        // Must out-rank the examination window, which is itself always on top.
        .always_on_top(true)
        .center()
        .focused(true)
        .build();

    let window = match built {
        Ok(window) => window,
        Err(error) => {
            log::error!("could not open the unlock prompt: {error}");
            state.lockdown.end_unlock();
            return;
        }
    };

    let handle = app.clone();
    window.on_window_event(move |event| {
        if matches!(event, WindowEvent::Destroyed) {
            let state = handle.state::<AppState>();
            state.lockdown.end_unlock();
            if let Some(exam) = handle.get_webview_window("exam") {
                let _ = exam.set_always_on_top(true);
                let _ = exam.set_focus();
            }
        }
    });
}
