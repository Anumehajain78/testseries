"""Stand-in for the lab clients.

Liveness is derived from ``last_heartbeat_at``, so seeded workstations correctly
go offline about ninety seconds after the seed runs — nothing is reporting. That
is the right behaviour and the wrong demo: the monitor is the screen most worth
looking at, and it is only alive for a minute and a half.

This script does what the Tauri lab client will do once it exists: report that a
machine is still there. It preserves the seed's deliberate mix, so the same
machines stay healthy, in warning, or dark, and the monitor keeps showing a
realistic room rather than a wall of green.

    python -m scripts.simulate_heartbeats             # one pass
    python -m scripts.simulate_heartbeats --watch     # every 10s until stopped

Delete this when the lab client sends real heartbeats.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.models import Computer, ExamSession  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.utils.clock import utcnow  # noqa: E402


def beat_once() -> tuple[int, int, int]:
    """Refresh heartbeats, keeping each machine in the band it was seeded into."""
    now = utcnow()
    online = warning = offline = 0

    with SessionLocal() as db:
        machines = db.execute(select(Computer)).scalars().all()
        for machine in machines:
            # A machine the seed left dark stays dark: an offline workstation is
            # part of what the monitor is for.
            if machine.last_heartbeat_at is None:
                offline += 1
                continue

            if machine.position % 13 == 0:
                machine.last_heartbeat_at = now - timedelta(minutes=6)   # offline
                offline += 1
            elif machine.position % 5 == 0:
                machine.last_heartbeat_at = now - timedelta(seconds=45)  # warning
                warning += 1
            else:
                machine.last_heartbeat_at = now - timedelta(seconds=3)   # online
                online += 1

        # Sessions carry their own heartbeat, since a session can outlive the
        # machine it started on.
        sessions = db.execute(select(ExamSession)).scalars().all()
        by_computer = {machine.id: machine for machine in machines}
        for session in sessions:
            machine = by_computer.get(session.computer_id) if session.computer_id else None
            if machine is not None:
                session.last_heartbeat_at = machine.last_heartbeat_at

        db.commit()

    return online, warning, offline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="keep beating until interrupted")
    parser.add_argument("--interval", type=int, default=10, help="seconds between passes")
    args = parser.parse_args()

    while True:
        online, warning, offline = beat_once()
        print(f"heartbeat: {online} online, {warning} warning, {offline} offline")
        if not args.watch:
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
