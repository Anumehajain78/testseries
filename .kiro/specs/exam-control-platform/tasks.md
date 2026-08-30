# Implementation Plan

- [x] 1. Extend the data model and type layer
  - Update `lib/types.ts` with `ConnectionStatus`, `QuestionType`, `AuditSeverity` enums and the `AnswerValue` discriminated union
  - Add `Computer`, `ActivityEntry`, and `ExamSession` interfaces
  - Extend `Question` (type, correctOptions), `Test` (description, assignedStudentIds, config, ExamConfig), `AuditEvent` (studentId, computerId, category, widened severity), and `ExamState` (version 2, computers, sessions, mockResultMode)
  - _Requirements: 16.1, 13.4, 4.6, 11.1, 17.1_

- [x] 2. Expand the mock data layer
  - [x] 2.1 Seed students, labs, and computers
    - Grow `seedStudents` to a realistic roster (~60) with branch/year/section/assigned lab values
    - Update `seedLabs` with computer counts and add `seedComputers` binding machine IDs (e.g. `LAB2-PC-01`) to students and connection states
    - _Requirements: 16.2, 16.4, 8.1, 9.1, 9.3_
  - [x] 2.2 Seed tests, sessions, questions, results, and audit events
    - Add mixed-type questions (mcq, multiple, text) and `config` to seed tests; populate `assignedStudentIds`
    - Add `seedSessions` with connection status, exam status, login/heartbeat times, warning counts, and activity timelines
    - Extend audit seed with studentId/computerId/category/severity and add a completed-test result set
    - Export `createSeedState()` returning `version: 2` state including computers, sessions, and `mockResultMode: false`
    - _Requirements: 16.2, 16.4, 6.3, 6.6, 10.1, 11.1_

- [x] 3. Extend the Exam Store provider
  - Update `providers.tsx` `safeState` to accept only `version === 2` and fall back to fresh seed otherwise
  - Extend `answerQuestion` to accept `AnswerValue`; update scoring in `submitExam` for single/multiple/text questions
  - Add session-aware actions: `startExam` sets `endsAt` and flips assigned sessions to in-progress; add helpers to set `mockResultMode`
  - Preserve existing `createTest`, `scheduleExam`, `dismissToast`, `resetDemo`, cross-tab sync, and toast behavior
  - _Requirements: 17.1, 17.2, 17.3, 17.4, 7.2, 13.5, 14.2_

- [x] 4. Add shared UI building blocks and derived selectors
  - Add `StatusDot` to `components/ui.tsx` mapping connection/lab states to color indicators
  - Create `lib/selectors.ts` with pure helpers to join sessions+computers+students into monitor rows, compute lab online counts, and apply monitor/audit filters
  - _Requirements: 19.3, 21.1, 6.5, 11.4, 9.1_

- [x] 5. Build the admin dashboard overview
  - Implement `/admin/page.tsx` using the store: welcome header, stat cards (live, scheduled, students online/assigned, warnings), today's examinations table with View/Monitor actions, and live lab status cards with color indicators
  - Wire View/Monitor actions to test detail and monitor routes
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 6. Build the tests management page
  - Implement `TestTable` and `/admin/tests/page.tsx` with columns, All/Scheduled/Live/Completed/Draft filters, Create Test button, row navigation to detail, and empty state
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 19.1_

- [x] 7. Build the create test form
  - Implement `/admin/tests/create/page.tsx` with Basic Information, Schedule, Lab Assignment, Students (with selected count), Exam Configuration, and Review sections
  - Validate required Basic Information and Schedule fields; wire Save Draft and Create Test to the store and navigate to the new test detail page
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

- [x] 8. Build the test details page
  - Implement `/admin/tests/[id]/page.tsx` with title, status badge, info cards (start, duration, students, lab, questions), and a roster table (roll, name, computer, connection, exam status)
  - Show Start/Edit/Monitor actions for scheduled tests and a not-found state for unknown ids
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 9. Implement the start-exam flow
  - Add a start confirmation `Modal` on the details page showing title, assigned student count, and consequence text
  - On confirm call `startExam` (Scheduled → Live), show success toast; on cancel leave status unchanged
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 10. Build live exam monitoring
  - [x] 10.1 Monitoring header, stats, and student monitor table
    - Implement `components/monitor.tsx` with `MonitorStats` and `StudentMonitor`; build `/admin/tests/[id]/monitor/page.tsx` with title, Live indicator, ExamTimer, stats (online/assigned, submitted, active, warnings, disconnected), and the monitor table
    - Add All/Active/Warning/Offline/Submitted filters using selectors and color-coded connection indicators
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 18.5_
  - [x] 10.2 Student detail panel and activity timeline
    - Implement `StudentDetailPanel` and `ActivityTimeline`; open panel on row activation showing student/computer details, exam status, login/exam-start/last-heartbeat times, warning count, and timeline
    - Add a display-only interval tick to refresh "time since last heartbeat"
    - _Requirements: 6.6, 19.1_

- [x] 11. Build the students management page
  - Implement `StudentTable` and `/admin/students/page.tsx` with roll/name/branch/year/status/assigned-lab columns, search by name or roll, year/branch/section filters, and empty state
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 19.1_

- [x] 12. Build the labs and computers page
  - Implement `components/labs.tsx` with `LabCard` and `ComputerGrid`; build `/admin/labs/page.tsx` showing lab cards (name, total, online) and a computer grid on selection
  - Render each computer with machine ID, assigned student, connection status color, and exam status; indicate labs with no online computers as no active exam
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 19.1_

- [x] 13. Build the results page
  - Implement `/admin/results/page.tsx` with submitted/average/highest stats, a ranked table (rank, student, roll, score, percentage, time taken, status), View Result action, a no-op Export control, and empty state
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 14. Build the audit logs page
  - Implement `/admin/audit/page.tsx` with a table (timestamp, student, computer, event, severity, details), severity indicators, All/Warnings/Critical/Connection/Exam Events filters, and empty state
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 15. Build the student waiting room
  - Implement `/student/waiting/page.tsx` and a `SystemCheck` component: platform name, assigned test title, student name, roll, assigned computer, connected status, and readiness checks
  - Show scheduled waiting message; when the test becomes Live, transition to the exam route; show empty state when no test assigned
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 19.2_

- [x] 16. Build the student exam interface
  - [x] 16.1 Exam layout, navigation, and question rendering
    - Implement `/student/exam/[id]/page.tsx` with top bar (platform, title, ExamTimer), `QuestionPalette` (Answered/Not Answered/Current), and `QuestionCard` rendering MCQ, multiple-choice, and text inputs
    - Persist answers via the store; provide Previous, Save & Next, and Submit controls; guard non-live tests with a closed-entry state
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.9, 19.2_
  - [x] 16.2 Timer warning and auto-submit
    - Wire ExamTimer urgency below the 10-minute warning threshold and auto-submit navigating to the submitted route at zero
    - _Requirements: 13.7, 13.8, 18.1, 18.2, 18.3, 18.4_

- [x] 17. Build the student submit flow and confirmation page
  - Implement `SubmitDialog` with answered/unanswered counts and finality warning; on confirm record submission (status Submitted) and navigate to submitted route; on cancel return to exam
  - Implement `/student/submitted/page.tsx` with success confirmation, test title, submission time, Submitted status, scores hidden unless `mockResultMode`, and empty state when no submission
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 15.1, 15.2, 15.3, 15.4_

- [x] 18. Wire navigation, polish, and verify the build
  - Verify end-to-end admin and student navigation and cross-tab live propagation on start; ensure hover/loading/empty states, dialogs, toasts, and badges are present
  - Apply restrained palette, status colors, and responsive layout for 1280/1440/1920 admin and 1366×768 exam; confirm accessible labels and keyboard operation
  - Run the Next.js build and `getDiagnostics` to confirm no type errors or broken routes
  - _Requirements: 20.1, 20.2, 20.3, 20.4, 21.1, 21.2, 21.3, 21.4, 21.5, 1.6_

- [x] 19. Add automated unit tests
  - [x] 19.1 Test exam timer math and expiry
    - Add tests for remaining-time-from-endsAt, warning threshold crossing, and single expiry invocation (justify and add Vitest before install)
    - _Requirements: 18.1, 18.3, 18.4_
  - [x] 19.2 Test scoring and filter selectors
    - Add tests for single/multiple/text scoring in submitExam and for monitor/audit filter selectors
    - _Requirements: 13.4, 14.2, 6.5, 11.4_
