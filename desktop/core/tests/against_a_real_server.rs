//! The client against a running examination server.
//!
//! Ignored by default, because it needs a server and a lab enrolment token and
//! most runs of the suite have neither. Run it when the protocol changes:
//!
//! ```text
//! EXAM_API=http://localhost:8000/api/v1 \
//! EXAM_LAB_TOKEN=<from POST /labs/{id}/enrolment-token> \
//! EXAM_MACHINE_ID=LAB1-PC-01 \
//!   cargo test -p exam-lab-core -- --ignored --nocapture --test-threads=1
//! ```
//!
//! Single-threaded on purpose. More than one of these enrols the same
//! workstation, and enrolling rotates its secret — which is correct of the
//! server and exactly what you want if a machine is re-imaged, but it means
//! two tests racing on one machine id invalidate each other's credential. The
//! failure looks like "Unknown machine or secret", which reads alarmingly like
//! a protocol bug and is not one.
//!
//! Worth having despite the setup. Everything else in this crate tests the
//! client against its own idea of the server; this tests it against the server.
//! The failure it exists to catch is a field renamed on one side only, which
//! looks like nothing until a workstation silently stops reporting.

use std::env;

use exam_lab_core::api::Api;
use exam_lab_core::events;

fn setting(name: &str) -> Option<String> {
    env::var(name).ok().filter(|value| !value.is_empty())
}

#[tokio::test]
#[ignore = "needs a running examination server"]
async fn a_machine_enrols_and_reports_in() {
    let Some(base) = setting("EXAM_API") else {
        eprintln!("EXAM_API not set; nothing to talk to");
        return;
    };
    let token = setting("EXAM_LAB_TOKEN").expect("EXAM_LAB_TOKEN is required");
    let machine_id = setting("EXAM_MACHINE_ID").expect("EXAM_MACHINE_ID is required");

    let api = Api::new(&base).expect("a client");

    // Two-stage enrolment: a token an administrator types once per lab, traded
    // for a secret belonging to this machine alone.
    let credential = api
        .enrol(&token, &machine_id, Some("integration-test"))
        .await
        .expect("enrolment should succeed");
    assert_eq!(credential.machine_id, machine_id);
    assert!(
        !credential.secret.is_empty(),
        "a secret must come back exactly once"
    );

    let issued = api
        .machine_token(&machine_id, &credential.secret)
        .await
        .expect("the secret should buy a token");
    assert!(!issued.access_token.is_empty());
    assert!(
        issued.expires_at > chrono::Utc::now(),
        "a token that has already expired is not a token"
    );

    api.heartbeat(&issued.access_token, &machine_id, None)
        .await
        .expect("the heartbeat endpoint should accept this machine");

    println!(
        "enrolled {machine_id}, token valid until {}",
        issued.expires_at
    );
}

#[tokio::test]
#[ignore = "needs a running examination server"]
async fn a_wrong_secret_is_refused_rather_than_accepted_quietly() {
    let Some(base) = setting("EXAM_API") else {
        return;
    };
    let machine_id = setting("EXAM_MACHINE_ID").expect("EXAM_MACHINE_ID is required");

    let api = Api::new(&base).expect("a client");
    let outcome = api.machine_token(&machine_id, "not-the-secret").await;

    let error = outcome.expect_err("a wrong secret must not produce a token");
    assert!(
        error.is_unauthorized(),
        "expected a 401, got {error} — a client that cannot tell a refusal from an \
         outage will retry for ever against a machine that has been revoked"
    );
}

#[tokio::test]
#[ignore = "needs a running examination server, and --test-threads=1"]
async fn the_event_names_are_ones_the_server_accepts() {
    // The names live in two repositories' worth of code — here and in
    // backend/app/schemas/enums.py. A typo is a 422 the client cannot act on
    // and an event the invigilator never sees.
    let Some(base) = setting("EXAM_API") else {
        return;
    };
    let token = setting("EXAM_LAB_TOKEN").expect("EXAM_LAB_TOKEN is required");
    let machine_id = setting("EXAM_MACHINE_ID").expect("EXAM_MACHINE_ID is required");
    let session = setting("EXAM_SESSION_ID").expect("EXAM_SESSION_ID is required");

    let api = Api::new(&base).expect("a client");
    let credential = api
        .enrol(&token, &machine_id, None)
        .await
        .expect("enrolment");
    let issued = api
        .machine_token(&machine_id, &credential.secret)
        .await
        .expect("a token");

    for name in [
        events::FOCUS_LOST,
        events::FOCUS_RESTORED,
        events::EXAM_CLIENT_CLOSED,
        events::CONNECTION_RESTORED,
    ] {
        api.report_event(
            &issued.access_token,
            session.parse().expect("a session uuid"),
            name,
            chrono::Utc::now(),
            None,
        )
        .await
        .unwrap_or_else(|error| panic!("the server refused {name}: {error}"));
    }
}

#[tokio::test]
async fn an_unreachable_server_is_told_apart_from_a_refusal() {
    // No server needed, and this one is not ignored: a client that reads an
    // outage as a revoked machine stops trying, and a workstation that stops
    // trying disappears from the floor plan during an examination.
    let api = Api::new("http://127.0.0.1:1/api/v1").expect("a client");
    let error = api
        .machine_token("LAB1-PC-01", "whatever")
        .await
        .expect_err("nothing is listening on port 1");

    assert!(
        error.is_unreachable(),
        "expected an unreachable error, got {error}"
    );
    assert!(!error.is_unauthorized(), "an outage is not a refusal");
}
