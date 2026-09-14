//! Keeping the candidate in the paper, and reporting it when they leave.
//!
//! Read the honest inventory before trusting any of this. What is enforced
//! here is: an undecorated, fullscreen, always-on-top window with no devtools
//! in release, a close request that is refused, and an in-page guard against
//! reload, print, save, view-source, context menu and clipboard. What is only
//! *observed* — reported to the server, not prevented — is the candidate
//! reaching another window at all.
//!
//! What is neither enforced nor observed, because a userspace application on a
//! machine the candidate physically controls cannot do it:
//!
//! * Alt-Tab, Super, Ctrl-Alt-F2 (virtual terminal), Ctrl-Alt-Del, and the
//!   equivalents on every desktop environment. The window manager routes these
//!   before any application sees them.
//! * Killing the process — from a second TTY, a task manager, or by pulling
//!   the power. The server sees the gap in heartbeats; that is the whole
//!   defence, and it is a detection, not a prevention.
//! * A second monitor, a phone, a printed sheet, or the machine next to them.
//! * Screenshots and screen recording.
//! * Booting a different operating system from a USB stick.
//!
//! `always_on_top` is the weakest claim of the lot: it is a hint to the window
//! manager. GNOME on Wayland restricts it, several tiling managers ignore it,
//! and a user with a keyboard shortcut bound to "always on top" can toggle it
//! off. The re-assert loop below fights that, and does not always win.
//!
//! The system this belongs to already assumes all of the above — that is why
//! there is an invigilator in the room and an append-only audit trail. This
//! client makes leaving noisy, not impossible.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tauri::{Manager, WebviewWindow, WindowEvent};

use exam_lab_core::client::{report_closing, LabClient};

/// The exact strings `app.services.machines.REPORTABLE` accepts. Anything else
/// comes back as a 422 and is never stored, so these are constants rather than
/// literals scattered across call sites.
// The event names moved to exam_lab_core::events, alongside the client that
// sends them, so the crate that talks to the server owns its own vocabulary.

/// How often the window re-asserts its own geometry.
///
/// Not a defence against a determined candidate — it is a defence against a
/// window manager that quietly drops the hint when a notification pops up, or
/// when the machine comes back from a blanked screen.
const REASSERT_SECONDS: u64 = 3;

pub struct Lockdown {
    /// True while an invigilator has the unlock prompt open. Without this the
    /// act of asking to be let out would itself be filed as a focus loss
    /// against the candidate, and the re-assert loop would drag the
    /// examination window back over the prompt the invigilator is typing into.
    unlocking: AtomicBool,
    focused: AtomicBool,
}

impl Lockdown {
    pub fn new() -> Self {
        Self {
            unlocking: AtomicBool::new(false),
            focused: AtomicBool::new(true),
        }
    }

    pub fn begin_unlock(&self) {
        self.unlocking.store(true, Ordering::SeqCst);
    }

    pub fn end_unlock(&self) {
        self.unlocking.store(false, Ordering::SeqCst);
    }

    pub fn is_unlocking(&self) -> bool {
        self.unlocking.load(Ordering::SeqCst)
    }
}

impl Default for Lockdown {
    fn default() -> Self {
        Self::new()
    }
}

/// Runs before anything the server sends, on every navigation within the
/// examination window.
///
/// Everything here is confined to the webview. It stops the shortcuts that
/// would let a candidate leave the paper *through the page* — reload losing an
/// unsaved answer, print-to-PDF of the question set, clipboard exfiltration of
/// the text. It cannot stop anything the window manager handles first, and it
/// is defeated entirely by a candidate who can reach a second browser, which is
/// why focus loss is reported rather than relied upon not to happen.
pub const GUARD_SCRIPT: &str = r#"
(function () {
  if (window.__examGuardInstalled) return;
  window.__examGuardInstalled = true;

  var swallow = function (event) { event.preventDefault(); event.stopPropagation(); return false; };

  document.addEventListener('contextmenu', swallow, true);
  document.addEventListener('copy', swallow, true);
  document.addEventListener('cut', swallow, true);
  document.addEventListener('paste', swallow, true);
  document.addEventListener('dragstart', swallow, true);

  document.addEventListener('keydown', function (event) {
    var key = (event.key || '').toLowerCase();
    var ctrl = event.ctrlKey || event.metaKey;

    // Reload and history. Losing the page mid-paper is recoverable — the
    // server holds every saved answer — but it costs the candidate minutes
    // they do not get back.
    if (key === 'f5' || (ctrl && key === 'r')) return swallow(event);
    if (event.altKey && (key === 'arrowleft' || key === 'arrowright')) return swallow(event);
    if (ctrl && (key === '[' || key === ']')) return swallow(event);

    // Inspector shortcuts. In a release build there is no inspector to open,
    // because the devtools feature is not compiled in; this keeps a debug
    // build from being usable as an exam client by accident.
    if (key === 'f12') return swallow(event);
    if (ctrl && event.shiftKey && (key === 'i' || key === 'j' || key === 'c')) return swallow(event);

    // Taking the paper out of the room.
    if (ctrl && (key === 'p' || key === 's' || key === 'u')) return swallow(event);

    // New windows and tabs. The webview has no tab strip, but the shortcuts
    // still reach the platform's webview on some versions.
    if (ctrl && (key === 'n' || key === 't' || key === 'w')) return swallow(event);
  }, true);

  // The examination server API needs a session UUID to file an invigilation
  // event against, and nothing in the contract lets this machine look one up.
  // So the candidate interface has to hand it over. None of the three sources
  // below exists in the web application today — this is written against a
  // change that has not been made, and until it is, focus events queue on the
  // desktop side and are never filed. See desktop/README.md.
  var reported = null;
  var findSession = function () {
    if (window.__EXAM_SESSION_ID__) return String(window.__EXAM_SESSION_ID__);
    var meta = document.querySelector('meta[name="exam-session-id"]');
    if (meta && meta.content) return meta.content;
    try {
      var stored = window.sessionStorage.getItem('examSessionId');
      if (stored) return stored;
    } catch (error) { /* storage can be disabled; not worth failing over */ }
    return null;
  };

  var offer = function () {
    var found = findSession();
    if (!found || found === reported) return;
    var invoke = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
    if (!invoke) return;
    invoke('bind_session', { sessionId: found }).then(function () {
      reported = found;
    }).catch(function () { /* the desktop side logs the reason */ });
  };

  offer();
  setInterval(offer, 1000);
})();
"#;

/// Wire one window to the reporting client.
pub fn attach(window: &WebviewWindow, client: Arc<LabClient>, lockdown: Arc<Lockdown>) {
    let handle = window.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::Focused(focused) => {
            if lockdown.is_unlocking() {
                return;
            }
            // The platform sends focus events in pairs on some window managers
            // — a blur immediately followed by a focus when a tooltip appears,
            // for instance. Filing both would put phantom warnings on a
            // candidate's record, so only a genuine change is reported.
            if lockdown.focused.swap(*focused, Ordering::SeqCst) == *focused {
                return;
            }

            let client = Arc::clone(&client);
            let focused = *focused;
            tauri::async_runtime::spawn(async move {
                if focused {
                    client
                        .report(
                            events::FOCUS_RESTORED,
                            Some("Returned to the examination window.".into()),
                        )
                        .await;
                } else {
                    client
                        .report(
                            events::FOCUS_LOST,
                            Some("The examination window lost focus.".into()),
                        )
                        .await;
                }
            });
        }

        WindowEvent::CloseRequested { api, .. } => {
            if lockdown.is_unlocking() {
                return;
            }
            // Undecorated windows have no close button, so anything arriving
            // here is Alt-F4, a window-manager close, or a logout. Refusing it
            // only covers the polite path: a SIGKILL does not produce this
            // event, and neither does the power switch.
            api.prevent_close();
            let client = Arc::clone(&client);
            tauri::async_runtime::spawn(async move {
                client
                    .report(
                        events::EXAM_CLIENT_CLOSED,
                        Some("A close was requested and refused.".into()),
                    )
                    .await;
            });
        }

        WindowEvent::Resized(_) => {
            if lockdown.is_unlocking() {
                return;
            }
            // Some desktops un-fullscreen a window when it is moved between
            // outputs or when a screen is unplugged. Put it back rather than
            // leaving a candidate looking at their own desktop.
            if handle.is_fullscreen().unwrap_or(true) {
                return;
            }
            let _ = handle.set_fullscreen(true);
        }

        _ => {}
    });
}

/// Re-applies the window hints a desktop environment may have dropped.
pub async fn hold_window(window: WebviewWindow, lockdown: Arc<Lockdown>) {
    let mut ticker = tokio::time::interval(Duration::from_secs(REASSERT_SECONDS));
    loop {
        ticker.tick().await;
        if lockdown.is_unlocking() {
            continue;
        }
        let _ = window.set_always_on_top(true);
        if !window.is_fullscreen().unwrap_or(true) {
            let _ = window.set_fullscreen(true);
        }
        // Focus is *not* re-asserted. Stealing it back every three seconds
        // would make the machine unusable for the invigilator and would not
        // stop a candidate anyway — they can read another window without it
        // having focus.
    }
}

/// Ends the session on the workstation once an invigilator has authorised it.
///
/// The report goes first and is awaited: `EXAM_CLIENT_CLOSED` arriving after
/// the process has gone is the same as it never arriving, and a machine that
/// vanishes from the monitor without a reason is one an invigilator has to walk
/// over and check.
pub async fn release(app: &tauri::AppHandle, client: Arc<LabClient>, who: &str) {
    // Belt and braces. The unlock prompt already suppressed the guard when it
    // opened, but if that ever stops being true the close refusal in `attach`
    // would leave the window up with an invigilator watching it not close.
    app.state::<crate::AppState>().lockdown.begin_unlock();
    report_closing(client, format!("Released by {who}.")).await;
    app.exit(0);
}

/// True when the examination window exists — used by the unlock flow, which
/// must not offer to release a machine that is still at the setup screen.
pub fn exam_window(app: &tauri::AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("exam")
}
