#!/usr/bin/env bash
#
# Put the examination platform on the college network.
#
# One machine runs the server; every lab workstation reaches it by typing its
# address. This script is what turns a checkout into that machine.
#
# It is deliberately not a container image. A college has one machine, one
# network and one person setting it up; a shell script they can read start to
# finish is worth more here than an orchestration layer they cannot.
#
#   ./deploy/lan-server.sh            # detect this machine's address and start
#   ./deploy/lan-server.sh 10.0.4.20  # or say which address to serve on
#   ./deploy/lan-server.sh --stop
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/deploy/run"
API_PORT="${EXAM_API_PORT:-8000}"
WEB_PORT="${EXAM_WEB_PORT:-3000}"
ENV_FILE="$ROOT/backend/.env.production"

# One worker serves requests one at a time — a request here is Python work, so
# throughput comes from processes. Measured: with one worker, 200 candidates
# signing in together gave 96 failures; with eight, none.
WORKERS="${EXAM_WORKERS:-8}"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
note() { printf '  %s\n' "$*"; }
die()  { printf '\n\033[31m%s\033[0m\n\n' "$*" >&2; exit 1; }

stop_everything() {
  say "Stopping"
  for name in api web; do
    local pidfile="$RUN_DIR/$name.pid"
    if [[ -f "$pidfile" ]]; then
      local pid; pid="$(cat "$pidfile")"
      if kill -0 "$pid" 2>/dev/null; then
        # The API runs a pool of workers; killing the group takes them too.
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
        note "stopped $name (pid $pid)"
      fi
      rm -f "$pidfile"
    fi
  done
  note "the database is left running; 'docker compose down' stops it"
  exit 0
}

[[ "${1:-}" == "--stop" ]] && stop_everything

# ---------------------------------------------------------------------------
# Which address the lab machines will type
# ---------------------------------------------------------------------------

HOST_IP="${1:-}"
if [[ -z "$HOST_IP" ]]; then
  HOST_IP="$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[\d.]+' | head -1 || true)"
fi
[[ -n "$HOST_IP" ]] || die "Could not work out this machine's network address. Pass it: ./deploy/lan-server.sh 192.168.1.50"

# A server on 127.0.0.1 is reachable from nowhere but itself, which is the one
# failure that looks like success until a lab machine tries it.
[[ "$HOST_IP" == "127."* ]] && die "$HOST_IP is this machine talking to itself. Lab machines cannot reach it. Pass the network address instead."

say "Serving on $HOST_IP"
note "console:  http://$HOST_IP:$WEB_PORT"
note "api:      http://$HOST_IP:$API_PORT/api/v1"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
  say "First run: writing $ENV_FILE"
  command -v openssl >/dev/null || die "openssl is needed once, to generate the signing secret."
  SECRET="$(openssl rand -hex 32)"

  # Carried over from the development configuration if there is one. Inventing
  # a password here would produce a file that cannot reach the database that
  # already exists, which is a first run that fails for a reason nobody asked
  # for.
  DB_URL="$(grep -m1 '^EXAM_DATABASE_URL=' "$ROOT/backend/.env" 2>/dev/null | cut -d= -f2- || true)"
  DB_URL="${DB_URL:-postgresql+psycopg://exam:exam_local_dev@localhost:5435/exam_control}"
  REDIS_URL="$(grep -m1 '^EXAM_REDIS_URL=' "$ROOT/backend/.env" 2>/dev/null | cut -d= -f2- || true)"
  REDIS_URL="${REDIS_URL:-redis://localhost:6380/0}"

  cat > "$ENV_FILE" <<ENV
# Written by deploy/lan-server.sh. Keep it. Never commit it.
#
# Changing EXAM_JWT_SECRET signs every candidate out at once, so it is
# generated once here and then left alone.
EXAM_ENVIRONMENT=production
EXAM_JWT_SECRET=$SECRET
EXAM_DATABASE_URL=$DB_URL
EXAM_REDIS_URL=$REDIS_URL
ENV
  chmod 600 "$ENV_FILE"
  note "generated a signing secret"
  note "database: $DB_URL"
  note "the compose password is a development one — change it, in Postgres and"
  note "in $ENV_FILE, before this holds real examinations"
fi

mkdir -p "$RUN_DIR"

# ---------------------------------------------------------------------------
# Checks worth making before a room full of people depends on this
# ---------------------------------------------------------------------------

say "Checking"
[[ -x "$ROOT/backend/.venv/bin/uvicorn" ]] || die "No backend virtualenv. Run: cd backend && python -m venv .venv && .venv/bin/pip install -e ."
command -v npm >/dev/null || die "npm is not installed."

set -a; # shellcheck disable=SC1090
source "$ENV_FILE"; set +a

if ! (cd "$ROOT/backend" && .venv/bin/python -c "
from sqlalchemy import create_engine, text
from app.core.config import get_settings
create_engine(str(get_settings().database_url)).connect().execute(text('select 1'))
" >/dev/null 2>&1); then
  die "Cannot reach the database. Start it with: docker compose up -d"
fi
note "database reachable"

(cd "$ROOT/backend" && .venv/bin/python -m alembic upgrade head >/dev/null)
note "schema up to date"

# ---------------------------------------------------------------------------
# Build and run
# ---------------------------------------------------------------------------

say "Building the console"
# NEXT_PUBLIC_* is substituted at build time, so the override a developer keeps
# in .env.local would be baked into the college's build — a console served from
# the school's address quietly asking localhost for its API. Cleared explicitly,
# because a real process variable outranks the file.
(cd "$ROOT/frontend" \
  && NEXT_PUBLIC_API_BASE_URL= NEXT_PUBLIC_API_PORT="$API_PORT" npm run build >/dev/null)
note "built"

say "Starting"
(
  cd "$ROOT/backend"
  # Passed per run rather than stored, so moving the server to a new address
  # cannot leave a stale origin behind that silently refuses half the lab.
  EXAM_CORS_ORIGINS="[\"http://$HOST_IP:$WEB_PORT\",\"http://localhost:$WEB_PORT\"]" \
  setsid .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port "$API_PORT" --workers "$WORKERS" \
    > "$RUN_DIR/api.log" 2>&1 &
  echo $! > "$RUN_DIR/api.pid"
)
(
  cd "$ROOT/frontend"
  setsid npm run start -- --hostname 0.0.0.0 --port "$WEB_PORT" \
    > "$RUN_DIR/web.log" 2>&1 &
  echo $! > "$RUN_DIR/web.pid"
)

for _ in $(seq 1 40); do
  sleep 1
  if curl -sf -m 2 "http://$HOST_IP:$API_PORT/health" >/dev/null \
     && curl -sf -m 2 -o /dev/null "http://$HOST_IP:$WEB_PORT/"; then
    say "Running"
    note "Lab machines open:  http://$HOST_IP:$WEB_PORT"
    note "Logs:               deploy/run/api.log, deploy/run/web.log"
    note "Stop:               ./deploy/lan-server.sh --stop"
    note ""
    note "If a lab machine cannot reach it, the firewall on THIS machine is"
    note "the usual reason. Allow the two ports, e.g. with ufw:"
    note "  sudo ufw allow $WEB_PORT/tcp && sudo ufw allow $API_PORT/tcp"
    exit 0
  fi
done

die "Started, but nothing answered on $HOST_IP within 40s. See deploy/run/api.log and deploy/run/web.log."
