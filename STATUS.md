# What is built, what is left

A plain checklist of the whole project.

- **Works** — done and tested
- **Half done** — partly working
- **Not started** — not built yet

**12 of 14 main phases finished.**

---

## What works today

All of this runs for real. The server does the work, not the browser.

### For teachers

| | |
| --- | --- |
| **Works** | **Log in.** Real password check. Teachers and students see different things. |
| **Works** | **Make a test.** Add questions, pick a lab, pick students. Saved as a draft first. |
| **Works** | **Schedule it.** Every student is given a computer automatically. You can see who is ready before you start. |
| **Works** | **Press Start.** All students enter together. The server sets the start and end time. |
| **Works** | **Register lab computers.** Each machine is enrolled once with a room code, then holds its own identity and reports in by itself. |
| **Works** | **Watch the room live.** Who is online, answering, submitted, or dropped off. Updates by itself. |
| **Works** | **Results and activity log.** Marks, ranking, and a record of what happened. |

### For students

| | |
| --- | --- |
| **Works** | **Log in and wait.** The waiting room checks the student, the computer and the connection. |
| **Works** | **Take the test.** Questions, timer, save and next, flag for review. Answers save to the server as they go. |
| **Works** | **Submit and get a receipt.** The paper locks. The server marks it. |
| **Works** | **Written answers.** Saved, then read and marked by a teacher on a marking screen. The total updates as marks are given. |

---

## Safety rules already enforced

Checked on the server, so changing the browser does not get around them.

- **Students cannot see the correct answers.** They are never sent to the student's computer. Checked in the browser during a live test.
- **Changing the computer clock does not give extra time.** The end time comes from the server.
- **Pressing Start twice does not extend the exam.**
- **If a student's internet dies, the exam still ends.** The server closes and submits the paper on time, on its own.
- **A student can only open their own paper.** Another student's link shows "not found", so they cannot even tell it exists.
- **Log out clears everything.** Important on shared lab computers.

---

## Small things still left

Quick jobs. Nothing here blocks a demo, but the first one would bite you in a real exam.

| | |
| --- | --- |
| **Works** | **Staying logged in.** Logins renew by themselves in the background, so nobody is signed out mid-exam. |
| **Works** | **Editing a draft.** Change anything — title, schedule, lab, students, questions — until candidates are given seats. After that it is locked, and the screen says so. |
| **Works** | **Add candidates from the screen.** One at a time, or paste a whole spreadsheet. Each new candidate gets a password, shown once — copy it before closing. |
| **Works** | **Import a roster.** A bad row no longer sinks the file: the good rows go in, and each bad one is listed with its line number and the reason. |
| **Works** | **Publish results.** Marks stay hidden until the exam cell releases them, one assessment at a time. Until now there was no way to release them at all — every candidate saw "scores withheld" for ever. |
| **Works** | **Export report.** Downloads the released marks as a spreadsheet. Withheld marks are left out rather than written as zero. |
| **Works** | **Run health check.** Reads what each workstation last reported and says, lab by lab, how many are online, how many have gone quiet, and how many have never reported at all. No button on the screens is fake any more. |
| **Works** | **Coding questions.** Candidates write a Python program; the server runs it against test cases and marks it a minute or so after they submit. Teachers set the examples candidates can see and the hidden cases they cannot. |
| **Works** | **Put it on the college network.** One command — `./deploy/lan-server.sh` — works out this machine's address, sets up its secrets, and starts everything so lab computers can reach it by typing that address. |

**One thing to know about running it for real:** start the server with several
workers — `uvicorn app.main:app --workers 8`. One worker serves requests one at
a time whatever else is tuned, because each request is mostly Python work. With
one worker, 200 candidates signing in together gave 104 sign-ins and 96
failures; with eight, all 200 got in, the slowest in about three seconds.

**One thing to know about running candidates' code:** this is the riskiest thing the system does, so the program runs shut inside a box with no network, no view of the server's files, and a limit on time and memory. It cannot reach the database, cannot read the password file, and cannot leave anything behind. If that box is not available on a machine, **no code runs at all** — the marks simply do not appear, rather than the program being run unprotected. Teachers can check on the Assessments screen whether a machine can run code.

**One thing to know about marks for programs:** they arrive a minute or so after a candidate submits, not instantly. Running sixty programs takes time, and nobody should wait at a screen for it. Until then the paper says "awaiting marking", the same as a written answer waiting for a teacher.

**One thing to know about the health check:** the server cannot ring a computer — computers report in, and the server remembers when each one last did. So the check reads those reports rather than pinging anything, and the screen says so. A machine nobody has set up yet is listed separately from one that was working and stopped, because those need different people.

**One thing to know about who may add students:** only the exam cell administrator can add, edit or import candidates. Teachers can see the list but not change it. Before, a teacher was blocked from pasting a roster but could still add the same people one form at a time — the buttons and the server now agree.

**One thing to know about logins:** renewing a login now cancels the old renewal token, so a stolen one stops working the moment the real user renews. Two devices stay separate — renewing on one does not sign the other out. Signing out now really ends the session: the old renewal token stops working the moment you press it, not whenever it happens to expire.

**One thing to know about speed:** the app used to reload everything after every change — 18 requests to learn that one exam's status moved. Now a change to one assessment re-reads only that assessment: 4 requests instead of 18. This matters most on the live monitor, which refreshes every few seconds while an exam is running. Creating a new assessment still reloads everything, because a new one has to appear in the list.

**How many students it holds:** measured, not guessed. Sixty candidates in one
lab all signing in at the same second: everyone got in, the slowest sign-in
took about a second, and the whole group was answering within six. Two hundred
at once: everyone got in, slowest about three seconds, whole group answering
within fifteen. Saving an answer stayed under half a second throughout. This
needs the server started with several workers — see above.

---

## Big things not finished

Two left. Both are about the lab machine rather than the server.

- **Desktop exam app (Tauri)** — *written but never built.* The whole app is in `desktop/`, but this machine cannot compile it: it needs system libraries only an administrator can install. See `desktop/README.md` for the one command, and expect first-build errors.
- **Cheating signals from the desktop app** — *blocked, and it needs a decision.* The desktop app can see a student switching away, but it has no way to ask the server which exam session the machine is showing, so it cannot report it. Heartbeats and the floor plan work; these events pile up on the machine and go nowhere. Someone has to choose how the machine learns its session.

---

## What to do next

1. **Install the build tools and compile the desktop app.** It is written; nobody has ever built it. `desktop/README.md` has the command.
2. **Decide how a lab machine learns which exam session it is showing.** Until then the desktop app can watch for cheating but cannot report it.
**Honest about the lock down:** the desktop app keeps the exam fullscreen, blocks the developer tools, and reports attempts to close it. It does **not** stop Alt+Tab, Ctrl+Alt+Del, killing the program, a phone on the desk, or a second screen. No software on the machine can. Invigilators still matter.

---

## How it got here

Each step kept the app working, so nothing was ever half broken.

1. Put all data changes behind one place in the code
2. Wrote the agreement between app and server, so they cannot drift apart
3. Added the database and real logins
4. Teacher screens started reading from the database
5. Creating and starting exams moved to the server
6. The student exam moved to the server, and answers stopped being visible
7. Live updates, so the monitor changes by itself
8. Deleted the fake data — the app now needs the real server

---

## Checks

`200` server tests and `20` app tests, all passing. Types, code style and the production build are clean.

```bash
cd backend  && ./.venv/bin/python -m pytest -q
cd frontend && npm run test && npx tsc --noEmit && npm run lint
```
