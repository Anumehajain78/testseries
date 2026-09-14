# Lab client

The locked-down examination browser that runs on each laboratory workstation.
A Tauri 2 shell around the existing Next.js candidate interface: it enrols the
machine once, holds a credential of its own, reports that it is still alive,
and tells the server when the candidate leaves the paper.

It is a frame around the web application, not a second copy of it. Every
question, answer and deadline still comes from the server over the same API the
browser uses.

---

## Status: half of it is compiled and tested, half has never been built

The crate is split in two, and the split is the point.

**`core/` — compiled, linted, formatted, and tested.** Enrolment, tokens,
heartbeats, the invigilation event queue and the credential store. It depends
on nothing but crates.io, so it builds anywhere a Rust toolchain does:

```sh
cargo test -p exam-lab-core        # 10 tests
cargo clippy --all-targets         # clean
cargo fmt --check                  # clean
```

It has also been run against a live examination server, which is the part that
matters. `core/tests/against_a_real_server.rs` enrols a workstation, trades the
secret for a token, sends a heartbeat, and files all four invigilation events —
verified landing in the server's audit trail as `FOCUS_LOST`,
`FOCUS_RESTORED`, `EXAM_CLIENT_CLOSED` and `CONNECTION_RESTORED`. Those tests
are `#[ignore]`d by default because they need a server; the header of that file
says how to run them, and why they need `--test-threads=1`.

**`src-tauri/` — never compiled.** The window: fullscreen, always-on-top, no
devtools. Building it needs webkit and dbus development headers, and installing
those needs root, which was not available where this was written. On a machine
with them:

```sh
sudo apt-get install -y libwebkit2gtk-4.1-dev libssl-dev librsvg2-dev \
  libayatana-appindicator3-dev build-essential curl wget file libdbus-1-dev pkg-config
cargo check -p exam-lab-client
```

Expect compile errors on that first build. The window code has been reviewed by
hand against the Tauri 2 API but never put through a compiler, and reading is
not the same as building — the core crate needed a missing dependency and a
signature fix the moment it was actually compiled, and that half had been
reviewed just as carefully.

Three specific things to check first, because they are the least certain:

1. `capabilities/exam-window.json` declares an empty `permissions` array. The
   examination window is a remote origin and needs no core permissions — only
   the `remote.urls` entry, which is what makes IPC possible at all. If the
   capability schema rejects an empty list, add `core:default` and accept the
   wider surface.
2. `tauri-plugin-global-shortcut`'s handler signature gained its third
   (`event`) parameter during the 2.x series. If the build complains about
   closure arity in `lib.rs`, that is why.
3. `commands::enrol` builds the examination window from inside an async
   command, i.e. off the main thread. Tauri dispatches this through the event
   loop, but it is the one runtime path here with no synchronous equivalent to
   fall back on.

---

## Building on Linux

```bash
sudo apt-get install -y libwebkit2gtk-4.1-dev libssl-dev librsvg2-dev \
  libayatana-appindicator3-dev build-essential curl wget file
```

Then a Rust toolchain (user-space, no root):

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install tauri-cli --version '^2'
```

And from this directory:

```bash
cargo tauri dev           # run it
cargo tauri build         # produce a .deb and an AppImage
cd src-tauri && cargo fmt && cargo clippy --all-targets
```

`src-tauri/icons/` holds the PNGs a Linux build needs. For Windows or macOS
bundles, generate the rest first:

```bash
cargo tauri icon src-tauri/icons/source.png
```

---

## Pointing it at a LAN server

Nothing is baked in at build time. On first run the client shows a setup window
asking for four things, and an administrator fills them in once per machine:

| Field | Example | Notes |
| --- | --- | --- |
| Examination server API | `http://10.0.4.12:8000/api/v1` | Include the `/api/v1` suffix, as `lab_client.py --api` does |
| Candidate interface | `http://10.0.4.12:3000` | Where Next.js is served; the window opens `/student` |
| Machine identifier | `LAB1-PC-01` | Must already be on the laboratory floor plan — the server refuses to invent a machine |
| Laboratory enrolment token | from the admin console | Valid twelve hours; typed here and never stored |

The API base and the candidate interface are asked for separately because they
are two processes on the LAN server, and a college may well put a reverse proxy
in front of one and not the other.

These are written to `enrolment.json` in the platform application-data
directory (`~/.config/edu.northbridge.examlabclient/` on Linux) with mode
`0600`, and the directory `0700`. Set `EXAM_LAB_CLIENT_HOME` to put it
somewhere else — worth doing when imaging a lab, because the default is
per-user and otherwise every profile that signs in has to be enrolled
separately.

If the server later rejects the stored secret, the client wipes it and returns
to the setup window with an explanation rather than sitting in front of a
candidate looking normal while reporting nothing.

---

## What it does

**Enrolment**, in the two stages `app/services/machines.py` describes. An
administrator mints one short-lived token for the room; each machine trades it
via `POST /auth/machine/enrol` for a permanent secret of its own. That secret is
returned exactly once — only its hash is kept server-side — so it is written to
disk before the examination window opens, and a failure to write is reported
while the administrator is still standing there.

**Tokens.** `POST /auth/machine/token` on every run and whenever the cached one
is within sixty seconds of expiry, plus once more immediately on any `401` —
the expiry was measured by this machine's clock, and when the server disagrees
the server is right.

**Heartbeats** every 10 seconds, matching `EXAM_HEARTBEAT_INTERVAL_SECONDS`.
The server calls a machine *warning* at 30s and *offline* at 90s, so two beats
can be lost before anyone is sent to look. There is deliberately no backoff: a
client that backs off during an outage comes back after the candidate has
already been marked offline.

**Invigilation events**, using exactly the four names
`app.services.machines.REPORTABLE` accepts:

| Event | When |
| --- | --- |
| `FOCUS_LOST` | the examination window lost focus |
| `FOCUS_RESTORED` | it got it back |
| `EXAM_CLIENT_CLOSED` | a close was requested and refused, or an invigilator released the machine |
| `CONNECTION_RESTORED` | heartbeats started landing again after an outage |

`CONNECTION_LOST` is never sent, and cannot be: a client that is offline cannot
tell anyone it is offline. The server derives it from the silence.

**An invigilator's way out.** `Ctrl+Alt+Shift+U` opens a prompt that signs in
against `POST /auth/login` and releases the machine if the account is `ADMIN`
or `FACULTY`. A candidate's own credentials authenticate fine and are then
refused on the role.

---

## How the client learns its session id — and why it works this way

`POST /sessions/{session_id}/events` needs a session UUID, and **no endpoint
gives a machine one.** `GET /me/sessions` needs a candidate's token; a machine
subject is refused everywhere except heartbeat and events. The heartbeat body
accepts an optional `sessionId` but never returns one.

That separation is deliberate and worth keeping. A workstation and the person
sitting at it are different subjects, and letting a machine credential resolve
a candidate's session would be a much worse trade than passing one identifier.

So the candidate interface hands it over. It already knows — it is showing that
paper — and the page publishes it:

```js
window.__EXAM_SESSION_ID__ = sessionId;   // frontend/lib/lab-client.ts
```

The injected guard script polls for it and calls `bind_session` over IPC. The
frontend sets it on entering an examination and **removes it on leaving**: a
stale id would have the client filing a candidate's focus events against a
paper they had already submitted.

The name is spelled in two places — `frontend/lib/lab-client.ts` and
`src-tauri/src/lockdown.rs` — and a test on the frontend side pins the exact
string, because the two drifting means invigilation stops working with nothing
anywhere to say so.

The URL is not a workaround: `/student/exam/[id]` carries an *exam* id, and
there is no machine-accessible way to turn one into a session id.

---

## What the lockdown actually does

Enforced:

* Fullscreen, undecorated, always-on-top, non-resizable window, kept out of the
  taskbar on Windows and most Linux desktops.
* No devtools in a release build — the `devtools` feature is not compiled in, so
  there is nothing to open, not merely a hidden shortcut.
* Close requests refused. With no title bar this is `Alt+F4`, a window-manager
  close, or a logout; each one is refused *and* reported.
* In-page: reload (`F5`, `Ctrl+R`), history navigation, print, save,
  view-source, new window/tab, inspector shortcuts, context menu, copy, cut,
  paste and drag.
* Fullscreen and always-on-top re-asserted every three seconds, because
  desktop environments drop both — on a screen unplug, a notification, or
  coming back from a blanked display.

Observed but **not** prevented — reported to the server and nothing more:

* The candidate reaching another window at all. `FOCUS_LOST` says it happened;
  it does not stop it happening.

Neither prevented nor observed, because a userspace application on a machine
somebody is physically sitting at cannot do it:

* `Alt+Tab`, the Super key, `Ctrl+Alt+F2` (virtual terminal), `Ctrl+Alt+Del`,
  and every desktop environment's equivalents. The window manager routes these
  before any application sees them.
* Killing the process — from a second TTY, a task manager, or the power switch.
  The gap in heartbeats is the entire defence, and it is a detection, not a
  prevention.
* A second monitor, a phone, a printed sheet, or the machine next to them.
* Screenshots and screen recording.
* Booting a different operating system from a USB stick.

`always_on_top` is the weakest claim of the lot. It is a *hint* to the window
manager: GNOME on Wayland restricts it, several tiling managers ignore it, and
a user with a shortcut bound to "always on top" can toggle it off. The
re-assert loop fights that and does not always win.

The unlock check is a convenience for the person with the keys, not a security
boundary — it runs on the machine it is protecting, and anyone who can patch
the binary can skip it.

None of this is a surprise to the system it belongs to. That is why there is an
invigilator in the room and an append-only audit trail. **This client makes
leaving noisy, not impossible.**

---

## Where the logs are

`tauri-plugin-log` writes to the platform log directory
(`~/.local/share/edu.northbridge.examlabclient/logs/exam-lab-client.log` on
Linux) as well as stderr. A lab machine has no console anyone looks at, so the
file is the point: when somebody asks why a workstation showed as offline for
four minutes, it is the only record on the machine's side of it.

---

## Layout

```
src/                      the two local pages — setup and the unlock prompt
src-tauri/
  capabilities/           default.json (local windows), exam-window.json (remote)
  src/
    api.rs                the five endpoints this client calls, and nothing else
    client.rs             token cache, heartbeat loop, event queue
    commands.rs           what the pages may ask for
    config.rs             the credential on disk, and its permissions
    lockdown.rs           window rules, the guard script, the honest inventory
    windows.rs            setup, examination, unlock — and the order they happen in
```
