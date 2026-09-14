//! What a lab workstation does, with no window attached.
//!
//! Enrolment, tokens, heartbeats and the invigilation event queue. The GUI
//! shell lives in the `exam-lab-client` crate next door and depends on this
//! one; nothing here depends on it, or on Tauri, or on any system library
//! needing development headers.
//!
//! That split is not tidiness. The GUI needs webkit and dbus headers that only
//! root can install, so a machine without them cannot build the client at all
//! — and before this crate existed, that meant no part of the desktop client
//! had ever been compiled or tested. This half now is.

pub mod api;
pub mod client;
pub mod config;
pub mod events;
