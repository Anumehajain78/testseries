//! The file holding a workstation's machine secret.
//!
//! That secret is a long-lived credential: anything that can read it can
//! impersonate this workstation to the examination server for as long as the
//! machine stays enrolled. A lab machine is shared, physically reachable, and
//! signed into by whoever is sitting at it, so the permissions on this file are
//! the whole of its protection on disk.
//!
//! These also pin the recovery behaviour, which matters more than it looks: a
//! workstation that refuses to start because its store is corrupt needs
//! somebody with a shell, in a room where an examination is about to begin.

use std::fs;

use exam_lab_core::config::{self, Enrolment};

fn sample() -> Enrolment {
    Enrolment {
        api_base_url: "http://10.0.4.12:8000/api/v1".into(),
        candidate_url: "http://10.0.4.12:3000".into(),
        machine_id: "LAB1-PC-07".into(),
        hostname: Some("lab1-pc-07".into()),
        secret: "a-long-lived-machine-credential".into(),
    }
}

#[test]
fn what_is_saved_is_what_comes_back() {
    let dir = tempfile::tempdir().unwrap();
    config::save(dir.path(), &sample()).unwrap();

    let loaded = config::load(dir.path()).expect("an enrolment that was just written");
    assert_eq!(loaded.machine_id, "LAB1-PC-07");
    assert_eq!(loaded.secret, "a-long-lived-machine-credential");
    assert_eq!(loaded.api_base_url, "http://10.0.4.12:8000/api/v1");
}

#[test]
fn a_machine_that_was_never_enrolled_reads_as_not_enrolled() {
    let dir = tempfile::tempdir().unwrap();
    assert!(config::load(dir.path()).is_none());
}

#[test]
fn a_corrupt_store_reads_as_not_enrolled_rather_than_failing() {
    // An administrator can re-enrol in thirty seconds. A workstation that
    // refuses to start needs somebody with a shell, in a room where an
    // examination is about to begin.
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("enrolment.json"), "{ this is not json").unwrap();
    assert!(config::load(dir.path()).is_none());
}

#[test]
fn forgetting_a_machine_that_was_never_enrolled_is_not_an_error() {
    let dir = tempfile::tempdir().unwrap();
    config::forget(dir.path()).expect("forgetting nothing should succeed");
}

#[test]
fn forgetting_removes_the_secret() {
    let dir = tempfile::tempdir().unwrap();
    config::save(dir.path(), &sample()).unwrap();
    config::forget(dir.path()).unwrap();
    assert!(config::load(dir.path()).is_none());
}

#[cfg(unix)]
#[test]
fn the_secret_is_never_world_readable() {
    use std::os::unix::fs::PermissionsExt;

    let dir = tempfile::tempdir().unwrap();
    config::save(dir.path(), &sample()).unwrap();

    let mode = fs::metadata(dir.path().join("enrolment.json"))
        .unwrap()
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(
        mode, 0o600,
        "the machine secret must be readable only by its owner"
    );

    let dir_mode = fs::metadata(dir.path()).unwrap().permissions().mode() & 0o777;
    assert_eq!(
        dir_mode, 0o700,
        "the directory must not be listable by others"
    );
}

#[cfg(unix)]
#[test]
fn a_store_left_open_by_an_earlier_version_is_tightened_on_write() {
    // Upgrades happen on machines that already have a file. Writing without
    // fixing the mode would leave the old, looser permissions in place for the
    // life of the machine.
    use std::os::unix::fs::PermissionsExt;

    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("enrolment.json");
    fs::write(&path, "{}").unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();

    config::save(dir.path(), &sample()).unwrap();

    let mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode, 0o600);
}

#[test]
fn the_store_can_be_moved_for_a_shared_lab_image() {
    // The default is per-user, which on a shared image means enrolling the same
    // machine once per profile that signs in. The override is what a college
    // sets during imaging to avoid that.
    let dir = tempfile::tempdir().unwrap();
    let elsewhere = tempfile::tempdir().unwrap();

    // SAFETY: single-threaded test, and the variable is read immediately.
    unsafe { std::env::set_var("EXAM_LAB_CLIENT_HOME", elsewhere.path()) };
    let resolved = config::store_dir(dir.path());
    unsafe { std::env::remove_var("EXAM_LAB_CLIENT_HOME") };

    assert_eq!(resolved, elsewhere.path());
}

#[test]
fn without_the_override_the_platform_directory_is_used() {
    let dir = tempfile::tempdir().unwrap();
    unsafe { std::env::remove_var("EXAM_LAB_CLIENT_HOME") };
    assert_eq!(config::store_dir(dir.path()), dir.path());
}
