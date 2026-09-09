# What is built, what is left

A plain checklist of the whole project.

- **Works** — done and tested
- **Half done** — partly working
- **Not started** — not built yet

**9 of 14 main phases finished.**

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

**One thing to know about the health check:** the server cannot ring a computer — computers report in, and the server remembers when each one last did. So the check reads those reports rather than pinging anything, and the screen says so. A machine nobody has set up yet is listed separately from one that was working and stopped, because those need different people.

**One thing to know about who may add students:** only the exam cell administrator can add, edit or import candidates. Teachers can see the list but not change it. Before, a teacher was blocked from pasting a roster but could still add the same people one form at a time — the buttons and the server now agree.

**One thing to know about logins:** when a login is renewed, the old renewal token is not cancelled — it keeps working until it runs out on its own. Cancelling it needs a bit more work on the server. Worth doing before real exams.

**One thing to know about speed:** the app reloads all its data after every change. Fine with a few tests, slow with a few hundred. Worth tidying before the college actually uses it.

---

## Big things not started

Always planned for later. These are the difference between a working web app and a real exam hall system.

- **Desktop exam app (Tauri)** — the real lock down. A browser alone cannot stop Alt+Tab.
- **Cheating signals from the desktop app** — the server records them now, but only a desktop app can actually notice a student switching away.
- **Coding questions** — running student code safely, with time and memory limits.
- **Load testing** — 60 students in one lab, then 200 across labs.
- **Install on the college network.**

---

## What to do next

1. **Build the desktop exam app.** The biggest remaining piece, and now unblocked — the machine side of the server is done and it can enrol like any other client.

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
