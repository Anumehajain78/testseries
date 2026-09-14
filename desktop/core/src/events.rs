//! The invigilation events the server accepts.
//!
//! Named here rather than as string literals at each call site, and checked
//! against `backend/app/schemas/enums.py`: a typo is a 422 the client cannot
//! act on and an event the invigilator never sees.
//!
//! `CONNECTION_LOST` is deliberately absent even though the server defines it.
//! A client that has lost its connection cannot report having lost it — the
//! server infers that from a heartbeat that stopped arriving, which is the
//! only way it could ever be known.

pub const FOCUS_LOST: &str = "FOCUS_LOST";
pub const FOCUS_RESTORED: &str = "FOCUS_RESTORED";
pub const EXAM_CLIENT_CLOSED: &str = "EXAM_CLIENT_CLOSED";
pub const CONNECTION_RESTORED: &str = "CONNECTION_RESTORED";
