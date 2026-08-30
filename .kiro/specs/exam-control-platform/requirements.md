# Requirements Document

## Introduction

The College Exam Control Platform is a frontend-only web application for managing centralized examinations conducted in physical college computer labs. It provides two coordinated experiences: an administration console for faculty and exam-cell staff, and a focused examination client for students. The platform simulates the full examination lifecycle — scheduling a test, students checking into a waiting room, faculty observing connected lab computers, starting the test, students taking the exam, live invigilation monitoring, submission, and post-exam results and audit review.

This phase delivers the frontend only. No backend, API, real authentication, code execution, or external infrastructure is built. All data is served from an isolated mock data layer, and all lifecycle transitions are simulated with client-side state so a real backend (REST/WebSocket) can replace the layer later without rewriting the UI. The project is built on the existing initialized Next.js application in the `frontend/` directory using TypeScript and Tailwind CSS, and reuses already-installed dependencies.

## Glossary

- **Platform**: The complete College Exam Control Platform frontend application.
- **Admin Console**: The faculty/exam-cell administration experience rooted at the `/admin` route.
- **Student Client**: The student examination experience rooted at the `/student` route.
- **Exam Store**: The client-side state management layer (React context/provider backed by browser storage) that holds all simulated platform data and lifecycle state.
- **Mock Data Layer**: The isolated set of seed data modules and TypeScript types under `frontend/lib` (or `frontend/data`) that supplies initial data to the Exam Store.
- **Test**: A scheduled examination definition, including metadata, schedule, assigned lab, assigned students, configuration, and questions.
- **Exam Status**: The lifecycle state of a Test, one of: Draft, Scheduled, Live, Completed.
- **Student Exam Status**: The per-student progress state within a Test, one of: Not Ready, Ready, Taking Test, Submitted.
- **Connection Status**: The simulated network state of a lab computer, one of: Online, Warning, Offline.
- **Lab**: A physical computer laboratory containing a fixed set of lab computers.
- **Computer**: A single workstation within a Lab, identified by a Machine ID, optionally assigned to a Student.
- **Student**: A registered examination candidate record.
- **Question**: An exam item of a supported type, one of: MCQ (single choice), Multiple Choice (multi select), Text Answer.
- **Exam Timer**: The reusable countdown component driven by a shared session end time, supporting a warning threshold and automatic submission at zero.
- **Monitoring Dashboard**: The live invigilation view at `/admin/tests/[id]/monitor`.
- **Audit Event**: A recorded lifecycle or invigilation event with a severity of Info, Warning, or Critical.
- **Toast**: A transient non-blocking notification surfaced after an action.
- **Warning Threshold**: The remaining-time value (10 minutes) below which the Exam Timer signals urgency.

## Requirements

### Requirement 1: Project foundation and constraints

**User Story:** As a developer, I want the platform built on the existing Next.js project without backend dependencies, so that the frontend can be reviewed now and connected to a backend later.

#### Acceptance Criteria

1. THE Platform SHALL be implemented within the existing `frontend/` Next.js project using TypeScript for all source files.
2. THE Platform SHALL style all interfaces using Tailwind CSS and the currently installed dependencies.
3. WHERE a required capability depends on a library that is not installed, THE Platform SHALL document the justification before that library is added.
4. THE Platform SHALL source all displayed data from the Mock Data Layer through the Exam Store.
5. THE Platform SHALL exclude backend services, network API calls, real authentication, and code execution from the implementation.
6. WHEN the project build command runs, THE Platform SHALL compile without type errors and without broken routes.

### Requirement 2: Admin dashboard overview

**User Story:** As a faculty member, I want an overview dashboard, so that I can monitor and manage today's examinations at a glance.

#### Acceptance Criteria

1. WHEN a user opens the `/admin` route, THE Admin Console SHALL display a header containing the platform name, the current faculty identity, a notification control, and a profile menu control.
2. WHEN a user opens the `/admin` route, THE Admin Console SHALL display a persistent sidebar with navigation entries for Dashboard, Tests, Students, Labs & Computers, Results, Audit Logs, and Settings.
3. WHEN a user opens the `/admin` route, THE Admin Console SHALL display summary statistics for count of Live Tests, count of Scheduled Tests, count of students online out of assigned, and count of warnings.
4. WHEN a user opens the `/admin` route, THE Admin Console SHALL display a table of the current day's examinations listing subject, lab, start time, duration, student count, Exam Status, and row actions.
5. WHERE a listed examination has Exam Status Live, THE Admin Console SHALL provide a Monitor action and a View action for that examination.
6. WHEN a user opens the `/admin` route, THE Admin Console SHALL display per-lab live status using distinct Online, Warning, and Offline color indicators.

### Requirement 3: Tests management

**User Story:** As a faculty member, I want a test management page, so that I can browse and open all examinations by lifecycle state.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/tests` route, THE Admin Console SHALL display a table listing each Test with subject, date, start time, duration, lab, student count, Exam Status, and actions.
2. WHEN a user opens the `/admin/tests` route, THE Admin Console SHALL provide filters for All, Scheduled, Live, Completed, and Draft.
3. WHEN a user selects a filter, THE Admin Console SHALL display only the Tests whose Exam Status matches the selected filter.
4. WHEN a user activates a Test row, THE Admin Console SHALL navigate to the `/admin/tests/[id]` route for that Test.
5. WHEN a user activates the Create Test control, THE Admin Console SHALL navigate to the `/admin/tests/create` route.
6. IF no Test matches the active filter, THEN THE Admin Console SHALL display an empty state message.

### Requirement 4: Create test

**User Story:** As a faculty member, I want a structured create-test form, so that I can define a complete examination and save it.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/tests/create` route, THE Admin Console SHALL present sections for Basic Information, Schedule, Lab Assignment, Students, Exam Configuration, and Review.
2. THE Admin Console SHALL capture test name, subject, description, and instructions within the Basic Information section.
3. THE Admin Console SHALL capture date, start time, and duration within the Schedule section.
4. THE Admin Console SHALL capture a selected Lab within the Lab Assignment section.
5. THE Admin Console SHALL capture a student selection and display the count of selected students within the Students section.
6. THE Admin Console SHALL capture questions-per-student, randomize-questions, randomize-options, allow-navigation, and auto-submit-on-expiry within the Exam Configuration section.
7. THE Admin Console SHALL display a summary of all entered values within the Review section before creation.
8. WHEN a user activates Create Test, THE Exam Store SHALL persist the new Test with Exam Status Draft and THE Admin Console SHALL navigate to that Test's `/admin/tests/[id]` route.
9. WHEN a user activates Save Draft, THE Exam Store SHALL persist the new Test with Exam Status Draft.
10. IF a required field in the Basic Information or Schedule section is empty when the user activates Create Test, THEN THE Admin Console SHALL display a validation message and SHALL prevent creation.

### Requirement 5: Test details

**User Story:** As a faculty member, I want a detailed test overview, so that I can review configuration and readiness before starting.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/tests/[id]` route, THE Admin Console SHALL display the Test title and a status badge reflecting the current Exam Status.
2. WHEN a user opens the `/admin/tests/[id]` route, THE Admin Console SHALL display information cards for start time, duration, student count, lab, and question count.
3. WHEN a user opens the `/admin/tests/[id]` route, THE Admin Console SHALL display a student table listing roll number, student name, assigned Computer, Connection Status, and Student Exam Status.
4. WHERE the Exam Status is Scheduled, THE Admin Console SHALL provide Start Test, Edit Test, and Monitor Exam actions.
5. IF the requested Test identifier does not match any Test, THEN THE Admin Console SHALL display a not-found state.

### Requirement 6: Live exam monitoring

**User Story:** As an invigilator, I want a real-time monitoring dashboard, so that I can observe every student's connection and exam activity during a live test.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/tests/[id]/monitor` route for a Live Test, THE Monitoring Dashboard SHALL display the Test title, a Live indicator, and the remaining time from the Exam Timer.
2. WHEN a user opens the Monitoring Dashboard, THE Monitoring Dashboard SHALL display statistics for students online out of assigned, count submitted, count active, count of warnings, and count disconnected.
3. WHEN a user opens the Monitoring Dashboard, THE Monitoring Dashboard SHALL display a student monitor listing Computer, student name, roll number, Connection Status, Student Exam Status, activity indicator, and time since last heartbeat.
4. THE Monitoring Dashboard SHALL provide filters for All, Active, Warning, Offline, and Submitted.
5. WHEN a user selects a monitor filter, THE Monitoring Dashboard SHALL display only student rows matching the selected filter.
6. WHEN a user activates a student row, THE Monitoring Dashboard SHALL open a panel showing student details, Computer details, Student Exam Status, login time, exam start time, last heartbeat, warning count, and an activity timeline.
7. THE Monitoring Dashboard SHALL represent Online, Warning, and Offline Connection Status using distinct color indicators.

### Requirement 7: Start exam flow

**User Story:** As a faculty member, I want a guarded start-test action, so that I can release the examination to all connected students at once.

#### Acceptance Criteria

1. WHEN a user activates Start Test, THE Admin Console SHALL display a confirmation dialog stating the Test title, the count of assigned students, and the consequence that the examination begins for all connected students.
2. WHEN a user confirms the start dialog, THE Exam Store SHALL change the Test's Exam Status from Scheduled to Live and SHALL set the shared session end time from the Test duration.
3. WHEN the Test becomes Live, THE Admin Console SHALL display a success Toast confirming the examination started.
4. WHEN a user cancels the start dialog, THE Admin Console SHALL close the dialog and SHALL leave the Exam Status unchanged.
5. WHEN the Test becomes Live, THE Student Client SHALL release checked-in students from the waiting room into the examination.

### Requirement 8: Student management

**User Story:** As a faculty member, I want a student management page, so that I can browse and locate candidate records.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/students` route, THE Admin Console SHALL display a table listing roll number, name, branch, year, status, and assigned Lab for each Student.
2. THE Admin Console SHALL provide a search control that filters the Student table by name or roll number.
3. THE Admin Console SHALL provide filters for year, branch, and section.
4. WHEN a user enters search text, THE Admin Console SHALL display only Students matching the entered text.
5. IF no Student matches the active search or filter, THEN THE Admin Console SHALL display an empty state message.

### Requirement 9: Labs and computers

**User Story:** As a faculty member, I want a labs-and-computers view, so that I can see the physical readiness of each lab and workstation.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/labs` route, THE Admin Console SHALL display a card per Lab showing lab name, total computer count, and online computer count.
2. WHEN a user activates a Lab card, THE Admin Console SHALL display a computer grid for that Lab.
3. THE Admin Console SHALL display each Computer in the grid with its Machine ID, assigned Student, Connection Status, and Student Exam Status.
4. THE Admin Console SHALL represent each Computer's Connection Status using distinct Online, Warning, and Offline color indicators.
5. IF a Lab has no computers online, THEN THE Admin Console SHALL indicate the Lab has no active exam.

### Requirement 10: Results

**User Story:** As a faculty member, I want a results dashboard, so that I can review outcomes for completed examinations.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/results` route, THE Admin Console SHALL display statistics for count of students submitted, average score, and highest score.
2. WHEN a user opens the `/admin/results` route, THE Admin Console SHALL display a ranked table listing rank, student name, roll number, score, percentage, time taken, and status.
3. THE Admin Console SHALL provide a View Result action for each ranked row.
4. THE Admin Console SHALL display an Export control that performs no file generation in this phase.
5. IF no results exist, THEN THE Admin Console SHALL display an empty state message.

### Requirement 11: Audit logs

**User Story:** As an exam-cell auditor, I want an event log page, so that I can review examination and invigilation events by severity.

#### Acceptance Criteria

1. WHEN a user opens the `/admin/audit` route, THE Admin Console SHALL display a table listing timestamp, student, Computer, event, severity, and details for each Audit Event.
2. THE Admin Console SHALL represent each Audit Event severity of Info, Warning, and Critical using distinct indicators.
3. THE Admin Console SHALL provide filters for All, Warnings, Critical, Connection, and Exam Events.
4. WHEN a user selects an audit filter, THE Admin Console SHALL display only Audit Events matching the selected filter.
5. IF no Audit Event matches the active filter, THEN THE Admin Console SHALL display an empty state message.

### Requirement 12: Student waiting room

**User Story:** As a student, I want a focused waiting room, so that I can confirm readiness and wait for the examination to start.

#### Acceptance Criteria

1. WHEN a student opens the `/student/waiting` route, THE Student Client SHALL display the platform name, the assigned Test title, the student name, the roll number, the assigned Computer, and a Connected status.
2. WHEN a student opens the `/student/waiting` route, THE Student Client SHALL display readiness checks for student verified, computer verified, connection stable, and exam client ready.
3. WHILE the assigned Test Exam Status is Scheduled, THE Student Client SHALL display a waiting message indicating the examination has not begun.
4. WHEN the assigned Test Exam Status becomes Live, THE Student Client SHALL transition the student to the `/student/exam/[id]` route for that Test.
5. IF no Test is assigned to the student, THEN THE Student Client SHALL display an empty state message.

### Requirement 13: Student exam interface

**User Story:** As a student, I want a dedicated examination environment, so that I can navigate and answer questions without distraction.

#### Acceptance Criteria

1. WHEN a student opens the `/student/exam/[id]` route for a Live Test, THE Student Client SHALL display a top bar with the platform name, the Test title, and the remaining time from the Exam Timer.
2. WHEN a student opens the exam interface, THE Student Client SHALL display a question navigation panel indicating Answered, Not Answered, and Current status per question.
3. WHEN a student selects a question in the navigation panel, THE Student Client SHALL display that question's content in the center area.
4. THE Student Client SHALL render answer inputs appropriate to the Question type for MCQ, Multiple Choice, and Text Answer questions.
5. WHEN a student records an answer, THE Exam Store SHALL persist the answer for that question and student.
6. THE Student Client SHALL provide Previous, Save and Next, and Submit Test controls.
7. WHILE the Exam Timer remaining time is below the Warning Threshold, THE Student Client SHALL display an urgency indication on the timer.
8. WHEN the Exam Timer reaches zero, THE Student Client SHALL submit the examination automatically and SHALL navigate to the `/student/submitted` route.
9. IF the assigned Test Exam Status is not Live, THEN THE Student Client SHALL display a closed-entry state and SHALL prevent answering.

### Requirement 14: Student submit flow

**User Story:** As a student, I want a confirmation before submitting, so that I do not submit unintentionally.

#### Acceptance Criteria

1. WHEN a student activates Submit Test, THE Student Client SHALL display a confirmation dialog stating the count of answered questions, the count of unanswered questions, and the consequence that returning to the examination is not possible after submission.
2. WHEN a student confirms submission, THE Exam Store SHALL record the submission for that student and Test and SHALL set the Student Exam Status to Submitted.
3. WHEN a student confirms submission, THE Student Client SHALL navigate to the `/student/submitted` route.
4. WHEN a student cancels the submission dialog, THE Student Client SHALL close the dialog and SHALL return the student to the examination.

### Requirement 15: Submission confirmation page

**User Story:** As a student, I want a submission confirmation page, so that I know my examination was received.

#### Acceptance Criteria

1. WHEN a student opens the `/student/submitted` route after submitting, THE Student Client SHALL display a confirmation that the examination was submitted successfully.
2. WHEN a student opens the `/student/submitted` route, THE Student Client SHALL display the Test title, the submission time, and a Submitted status.
3. WHERE mock result mode is disabled, THE Student Client SHALL exclude scores from the submission confirmation page.
4. IF no submission exists for the student, THEN THE Student Client SHALL display an empty state message.

### Requirement 16: Mock data architecture

**User Story:** As a developer, I want an isolated mock data layer with typed models, so that a backend can replace it later without UI changes.

#### Acceptance Criteria

1. THE Mock Data Layer SHALL define TypeScript types for Test, Student, Lab, Computer, Question, Exam Session, Audit Event, Exam Status, and Student Exam Status.
2. THE Mock Data Layer SHALL provide seed data for Tests, Students, Labs, Computers, Questions, Results, and Audit Events.
3. THE Mock Data Layer SHALL be isolated from presentation components so that seed sources can be replaced by data-access calls without changing component interfaces.
4. THE Mock Data Layer SHALL populate all seed data with realistic college examination values and SHALL exclude placeholder filler text.

### Requirement 17: Simulated state management

**User Story:** As a developer, I want clean client-side state, so that lifecycle transitions are simulated and later replaceable by live backend state.

#### Acceptance Criteria

1. THE Exam Store SHALL hold state for Exam Status, exam start, waiting-room release, timer session end, student submissions, Connection Status, and warning counts.
2. WHEN a lifecycle action occurs in the Admin Console, THE Exam Store SHALL update the shared state so that the Student Client reflects the change.
3. THE Exam Store SHALL expose its state through interfaces that can be backed by WebSocket or API sources without changing consuming components.
4. WHEN the Platform reloads, THE Exam Store SHALL restore its most recent simulated state from browser storage.

### Requirement 18: Exam timer

**User Story:** As a developer, I want a reusable server-replaceable timer, so that examination timing is consistent and later driven by server time.

#### Acceptance Criteria

1. THE Exam Timer SHALL compute remaining time from a shared session end time rather than from a per-client countdown origin.
2. WHILE the remaining time is at or above the Warning Threshold, THE Exam Timer SHALL display a normal state.
3. WHEN the remaining time falls below the Warning Threshold, THE Exam Timer SHALL display a warning state.
4. WHEN the remaining time reaches zero, THE Exam Timer SHALL invoke its expiry handler exactly once.
5. THE Exam Timer SHALL be implemented as a reusable component consumed by both the Student Client and the Monitoring Dashboard.

### Requirement 19: Reusable component structure

**User Story:** As a developer, I want modular components, so that pages compose shared building blocks rather than duplicating markup.

#### Acceptance Criteria

1. THE Platform SHALL implement admin building blocks including sidebar, header, stats card, test table, student table, lab card, computer grid, student monitor, and activity timeline as reusable components.
2. THE Platform SHALL implement exam building blocks including exam header, question navigation, question card, exam timer, submit dialog, waiting room, and system check as reusable components.
3. THE Platform SHALL implement shared UI building blocks including badges, tables, dialogs, empty states, loading states, and toasts as reusable components.
4. THE Platform SHALL compose route pages from the reusable components rather than embedding duplicated layout markup in each page.

### Requirement 20: Navigation and workflow simulation

**User Story:** As a reviewer, I want end-to-end navigation, so that I can walk through the admin and student workflows using simulated state.

#### Acceptance Criteria

1. THE Platform SHALL allow navigation across the sequence Admin Dashboard, Tests, Test Details, Start Test, and Monitoring Dashboard.
2. THE Platform SHALL allow navigation across the sequence Student Waiting Room, Exam Interface, Submit, and Submission Confirmation.
3. WHEN a user starts a Test in the Admin Console, THE Student Client SHALL reflect the Live state for the assigned students without a manual data reset.
4. THE Platform SHALL make every navigation control and primary action visibly respond on the frontend.

### Requirement 21: Interface quality and accessibility

**User Story:** As a reviewer, I want a production-quality interface, so that the platform feels like a real institutional product.

#### Acceptance Criteria

1. THE Platform SHALL present a restrained color system with distinct Online, Warning, and Offline status colors and consistent typography and spacing.
2. THE Platform SHALL provide hover states, loading states, empty states, confirmation dialogs, Toast notifications, and status badges across relevant interfaces.
3. THE Admin Console SHALL remain usable at viewport widths of 1280, 1440, and 1920 pixels.
4. THE Student Client exam interface SHALL remain usable at a viewport resolution of 1366 by 768 pixels.
5. THE Platform SHALL provide accessible labels for interactive controls and SHALL support keyboard operation of primary actions.
