//! The locked-down examination browser that runs on a laboratory workstation.
//!
//! Three things happen here and nowhere else: the machine learns who it is
//! (once, from an administrator), it says it is still alive (every ten
//! seconds, forever), and it reports what happened in front of it. Everything
//! a candidate actually sees is the existing web application, loaded from the
//! LAN server — this binary is a frame around it, not a second copy of it.

mod api;
mod client;
mod commands;
mod config;
mod lockdown;
mod windows;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use tauri::Manager;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

use client::LabClient;
use config::Enrolment;
use lockdown::Lockdown;

/// Opens the invigilator's release prompt.
///
/// Deliberately awkward, and deliberately not written down anywhere a
/// candidate sees: it is the only way out of the locked window that does not
/// involve a power button, so the cost of a candidate discovering it by
/// accident is an examination interrupted.
fn unlock_chord() -> Shortcut {
    Shortcut::new(
        Some(Modifiers::CONTROL | Modifiers::ALT | Modifiers::SHIFT),
        Code::KeyU,
    )
}

pub struct AppState {
    /// Resolved once at startup; every read and write of the credential goes
    /// through this rather than recomputing the path, so an override set in the
    /// environment cannot be honoured in one place and ignored in another.
    pub store_dir: PathBuf,
    pub enrolment: Mutex<Option<Enrolment>>,
    pub client: Mutex<Option<Arc<LabClient>>>,
    pub lockdown: Arc<Lockdown>,
    /// Why the setup screen is on display, when it is not simply a first run.
    pub notice: Mutex<Option<String>>,
}

pub fn run() {
    let chord = unlock_chord();

    tauri::Builder::default()
        .plugin(
            // A lab machine has no console anyone will ever look at, so the
            // file target is the point: when a technician is asked why a
            // workstation showed as offline for four minutes, this is the only
            // record on the machine's side of it.
            tauri_plugin_log::Builder::new()
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::LogDir {
                        file_name: Some("exam-lab-client".into()),
                    },
                ))
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Stderr,
                ))
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    // Pressed, not released: a chord that fires twice would
                    // open the prompt and then immediately try to open it
                    // again on the way up.
                    if shortcut == &chord && event.state() == ShortcutState::Pressed {
                        windows::open_unlock(app);
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            commands::setup_state,
            commands::enrol,
            commands::bind_session,
            commands::unlock,
            commands::dismiss_unlock,
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let store_dir = config::store_dir(&handle.path().app_data_dir()?);
            let enrolment = config::load(&store_dir);

            handle.manage(AppState {
                store_dir,
                enrolment: Mutex::new(enrolment.clone()),
                client: Mutex::new(None),
                lockdown: Arc::new(Lockdown::new()),
                notice: Mutex::new(None),
            });

            if let Err(error) = handle.global_shortcut().register(unlock_chord()) {
                // Another application, or the desktop environment itself, may
                // already hold the chord. Worth a loud line in the log and not
                // worth refusing to run an examination over — the alternative
                // way out is the power switch, which works either way.
                log::error!("could not register the unlock shortcut: {error}");
            }

            match enrolment {
                Some(enrolment) => {
                    if let Err(message) = windows::start_examination(&handle, &enrolment) {
                        log::error!("{message}");
                        windows::open_setup(&handle, Some(message))?;
                    }
                }
                None => {
                    windows::open_setup(&handle, None)?;
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("the examination client could not start");
}
