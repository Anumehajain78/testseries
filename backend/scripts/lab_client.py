"""A stand-in lab client.

This is what the Tauri application will do, minus the part only a desktop app
can: enrol once, hold its own secret, and report that it is still there.

It replaces the earlier `simulate_heartbeats.py`, which wrote liveness straight
into the database. That was a lie in a useful shape — it made the monitor look
alive while proving nothing about the path a real machine takes. This one goes
through the API exactly as a workstation will, so if enrolment or the heartbeat
endpoint breaks, this breaks too.

    # once per lab, as an administrator
    python -m scripts.lab_client enrol --lab "Advanced Computing Lab"

    # then, per machine
    python -m scripts.lab_client run --machine LAB1-PC-01

    # or drive a whole room at once, for demos
    python -m scripts.lab_client room --lab "Advanced Computing Lab"

Delete this when the real client exists.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://localhost:8000/api/v1"
#: Where each machine keeps its credential, as the real client will.
STORE = Path(__file__).resolve().parent / ".machine-credentials.json"

HEARTBEAT_SECONDS = 5


def call(path: str, body: dict | None = None, token: str | None = None, method: str = "POST") -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"cannot reach {API} — is the server running? ({error.reason})") from error


def _credentials() -> dict:
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def _remember(machine_id: str, secret: str) -> None:
    store = _credentials()
    store[machine_id] = secret
    STORE.write_text(json.dumps(store, indent=2) + "\n")


def sign_in(email: str, password: str) -> str:
    return call("/auth/login", {"email": email, "password": password})["accessToken"]


def enrol(args) -> int:
    """Mint a token and claim every machine in the room, as an admin would."""
    token = sign_in(args.email, args.password)
    labs = call("/labs", token=token, method="GET")
    lab = next((item for item in labs if item["name"].lower() == args.lab.lower()), None)
    if lab is None:
        raise SystemExit(f"no lab named {args.lab!r}. Known: {[item['name'] for item in labs]}")

    enrolment = call(f"/labs/{lab['id']}/enrolment-token", {}, token=token)
    print(f"enrolment token for {lab['name']} (valid until {enrolment['expiresAt']})")

    machines = call(f"/labs/{lab['id']}/computers", token=token, method="GET")
    for machine in machines:
        credential = call(
            "/auth/machine/enrol",
            {
                "enrolmentToken": enrolment["token"],
                "machineId": machine["machineId"],
                "hostname": machine.get("hostname"),
            },
        )
        _remember(credential["machineId"], credential["secret"])
    print(f"enrolled {len(machines)} machines; credentials saved to {STORE.name}")
    return 0


def _machine_token(machine_id: str) -> str:
    secret = _credentials().get(machine_id)
    if not secret:
        raise SystemExit(f"{machine_id} is not enrolled on this host. Run `enrol` first.")
    return call("/auth/machine/token", {"machineId": machine_id, "secret": secret})["accessToken"]


def run(args) -> int:
    """One machine, reporting until stopped."""
    token = _machine_token(args.machine)
    print(f"{args.machine}: reporting every {HEARTBEAT_SECONDS}s. Ctrl-C to stop.")
    beats = 0
    while True:
        try:
            call(f"/computers/{args.machine}/heartbeat", {"machineId": args.machine}, token=token)
            beats += 1
            print(f"\r{args.machine}: {beats} heartbeats sent", end="", flush=True)
            time.sleep(HEARTBEAT_SECONDS)
        except KeyboardInterrupt:
            print()
            return 0
        except SystemExit:
            # The token is short-lived; renew and carry on rather than dying.
            token = _machine_token(args.machine)


def room(args) -> int:
    """Every enrolled machine in a lab, for demonstrating the monitor.

    The seeded pattern is preserved: a few machines stay dark and a few report
    late, so the monitor shows a realistic room rather than a wall of green.
    """
    token = sign_in(args.email, args.password)
    labs = call("/labs", token=token, method="GET")
    lab = next((item for item in labs if item["name"].lower() == args.lab.lower()), None)
    if lab is None:
        raise SystemExit(f"no lab named {args.lab!r}")

    machines = [m["machineId"] for m in call(f"/labs/{lab['id']}/computers", token=token, method="GET")]
    known = _credentials()
    live = [m for m in machines if m in known]
    if not live:
        raise SystemExit("no enrolled machines in this lab. Run `enrol` first.")

    tokens = {machine: _machine_token(machine) for machine in live}
    print(f"{lab['name']}: {len(live)} machines reporting every {HEARTBEAT_SECONDS}s. Ctrl-C to stop.")

    while True:
        try:
            sent = 0
            for index, machine in enumerate(live, start=1):
                # Every thirteenth machine stays silent, so "offline" is
                # visible on the monitor and not just a theory.
                if index % 13 == 0:
                    continue
                call(f"/computers/{machine}/heartbeat", {"machineId": machine}, token=tokens[machine])
                sent += 1
            print(f"\r{sent} of {len(live)} machines reported", end="", flush=True)
            time.sleep(HEARTBEAT_SECONDS)
        except KeyboardInterrupt:
            print()
            return 0
        except SystemExit:
            tokens = {machine: _machine_token(machine) for machine in live}


def main() -> int:
    global API
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=API, help="API base URL")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, needs_lab, needs_machine in (
        ("enrol", enrol, True, False),
        ("run", run, False, True),
        ("room", room, True, False),
    ):
        cmd = sub.add_parser(name)
        cmd.set_defaults(handler=handler)
        if needs_lab:
            cmd.add_argument("--lab", required=True)
            cmd.add_argument("--email", default="admin@northbridge.edu")
            cmd.add_argument("--password", default="examcontrol")
        if needs_machine:
            cmd.add_argument("--machine", required=True)

    args = parser.parse_args()
    API = args.api.rstrip("/")
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
