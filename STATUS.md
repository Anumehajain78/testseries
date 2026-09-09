# What is built, what is left

A plain checklist of the whole project.

- **Works** — done and tested
- **Half done** — partly working
- **Not started** — not built yet

**8 of 14 main phases finished.**

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
| **Works** | **Watch the room live.** Who is online, answering, submitted, or dropped off. Updates by itself. |
| **Works** | **Results and activity log.** Marks, ranking, and a record of what happened. |

### For students

| | |
| --- | --- |
| **Works** | **Log in and wait.** The waiting room checks the student, the computer and the connection. |
| **Works** | **Take the test.** Questions, timer, save and next, flag for review. Answers save to the server as they go. |
| **Works** | **Submit and get a receipt.** The paper locks. The server marks it. |
| **Half done** | **Written answers.** Saved, but they get 0 marks — there is no screen yet for a teacher to mark them. |

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
| **Fix soon** | **Login expires after 30 minutes.** No renewal yet, so a teacher can get logged out in the middle of a 90 minute exam. |
| **Half done** | **"Edit test" button does nothing.** The server side already works; only the button needs connecting. |
| **Not started** | **Marking screen for written answers.** Needed before written questions can count. |
| **Not started** | **Buttons that are only for show.** Import roster, Export report, Run health check. |
| **Not started** | **Add and edit students from the screen.** They come from the seed file at the moment. |

**One thing to know:** the app reloads all its data after every change. Fine with a few tests, slow with a few hundred. Worth tidying before the college actually uses it.

---

## Big things not started

Always planned for later. These are the difference between a working web app and a real exam hall system.

- **Register lab computers** — each machine gets its own identity.
- **Desktop exam app (Tauri)** — the real lock down. A browser alone cannot stop Alt+Tab.
- **Cheating signals** — reporting when a student leaves the exam window. The server can already store these; nothing sends them yet.
- **Coding questions** — running student code safely, with time and memory limits.
- **Load testing** — 60 students in one lab, then 200 across labs.
- **Install on the college network.**

---

## What to do next

1. **Keep people logged in.** Finish login renewal so nobody is kicked out mid-exam.
2. **Connect the "Edit test" button.** The server part is done and tested.
3. **Register lab computers and send real heartbeats.** A helper script currently pretends the computers are alive. Needed before the desktop app.
4. **Build the desktop exam app.** The biggest remaining piece.

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

`148` server tests and `20` app tests, all passing. Types, code style and the production build are clean.

```bash
cd backend  && ./.venv/bin/python -m pytest -q
cd frontend && npm run test && npx tsc --noEmit && npm run lint
```
