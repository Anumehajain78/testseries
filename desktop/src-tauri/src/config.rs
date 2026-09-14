//! What a workstation remembers between runs.
//!
//! Exactly one file, holding everything enrolment produced. It is written with
//! restrictive permissions because the machine secret in it is a long-lived
//! credential: anything that can read it can impersonate this workstation to
//! the examination server for as long as the machine stays enrolled.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Overrides where the store lives.
///
/// The default is the per-user application data directory, which is wrong for a
/// shared laboratory image in one specific way: each Windows or Linux profile
/// that signs in gets its own copy, so the machine has to be enrolled once per
/// profile. Pointing this at a machine-wide path (`/var/lib/exam-lab-client`,
/// `C:\ProgramData\ExamLabClient`) during imaging fixes that, at the cost of
/// someone having to create the directory with the right ownership first.
const HOME_OVERRIDE: &str = "EXAM_LAB_CLIENT_HOME";

const FILE_NAME: &str = "enrolment.json";

/// Everything an administrator established the first time this machine ran.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Enrolment {
    /// Base of the REST API, including the version prefix — the same string the
    /// reference client takes as `--api`, e.g. `http://10.0.4.12:8000/api/v1`.
    pub api_base_url: String,
    /// Where the candidate interface is served from, e.g. `http://10.0.4.12:3000`.
    /// Separate from the API because the two are separate processes on the LAN
    /// server and a college may well put a reverse proxy in front of only one.
    pub candidate_url: String,
    /// Must already exist on the lab's floor plan; the server refuses to invent
    /// a machine, so this is typed to match the sticker on the case.
    pub machine_id: String,
    pub hostname: Option<String>,
    /// Returned by `/auth/machine/enrol` exactly once and unrecoverable
    /// afterwards — the server keeps only its hash.
    pub secret: String,
}

/// Resolves the store directory, creating it if this is a first run.
///
/// `app_data` is what Tauri reports for this platform; it is passed in rather
/// than looked up here so this module stays testable without an `App`.
pub fn store_dir(app_data: &Path) -> PathBuf {
    match std::env::var_os(HOME_OVERRIDE) {
        Some(path) if !path.is_empty() => PathBuf::from(path),
        _ => app_data.to_path_buf(),
    }
}

pub fn load(dir: &Path) -> Option<Enrolment> {
    let raw = fs::read_to_string(dir.join(FILE_NAME)).ok()?;
    match serde_json::from_str(&raw) {
        Ok(enrolment) => Some(enrolment),
        Err(error) => {
            // A corrupt store is treated as "not enrolled" rather than a hard
            // failure: an administrator can re-enrol in thirty seconds, whereas
            // a workstation that refuses to start needs someone with a shell.
            log::error!("ignoring unreadable enrolment store: {error}");
            None
        }
    }
}

pub fn save(dir: &Path, enrolment: &Enrolment) -> io::Result<()> {
    fs::create_dir_all(dir)?;
    restrict_dir(dir)?;

    let path = dir.join(FILE_NAME);
    // Created before it is written, so the permissions are already narrow by
    // the time the secret reaches the disk. Writing first and chmod-ing after
    // leaves a window in which the file is world-readable.
    let body = serde_json::to_string_pretty(enrolment).map_err(io::Error::other)?;
    create_private(&path)?;
    fs::write(&path, body + "\n")?;
    restrict_file(&path)
}

pub fn forget(dir: &Path) -> io::Result<()> {
    match fs::remove_file(dir.join(FILE_NAME)) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        other => other,
    }
}

#[cfg(unix)]
fn create_private(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .mode(0o600)
        .open(path)
        .map(drop)
}

#[cfg(not(unix))]
fn create_private(path: &Path) -> io::Result<()> {
    fs::File::create(path).map(drop)
}

#[cfg(unix)]
fn restrict_file(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}

#[cfg(unix)]
fn restrict_dir(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
}

// Windows inherits the ACL of the per-user AppData directory, which already
// excludes other unprivileged users. It does *not* exclude an administrator or
// anyone with physical access to the disk — the same is true of the 0600 file
// above, and neither is claimed to be more than it is. The secret is scoped to
// one machine and revoked by re-enrolling, which is the actual defence.
#[cfg(not(unix))]
fn restrict_file(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(not(unix))]
fn restrict_dir(_path: &Path) -> io::Result<()> {
    Ok(())
}

/// The workstation's own name, offered as the default at enrolment.
pub fn local_hostname() -> Option<String> {
    hostname::get().ok()?.into_string().ok()
}
