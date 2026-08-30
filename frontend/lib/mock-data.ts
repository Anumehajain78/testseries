import type {
  ActivityEntry,
  AuditEvent,
  Computer,
  ConnectionStatus,
  ExamSession,
  ExamState,
  Lab,
  Question,
  Result,
  Student,
  StudentExamStatus,
  Test,
} from "./types";
import { missingSessions } from "./sessions";

// ---------------------------------------------------------------------------
// Students
// ---------------------------------------------------------------------------

type RosterSeed = {
  name: string;
  program: string;
  semester: number;
  section: string;
  blocked?: boolean;
};

const roster: RosterSeed[] = [
  { name: "Aarav Mehta", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Diya Nair", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Kabir Singh", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Meera Joshi", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Rohan Das", program: "B.Tech CSE", semester: 3, section: "A", blocked: true },
  { name: "Sara Khan", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Vivaan Reddy", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Ananya Iyer", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Aditya Rao", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Ishita Gupta", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Arjun Kapoor", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Nisha Verma", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Karthik Menon", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Priya Shetty", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Rahul Chauhan", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Sneha Pillai", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Dhruv Malhotra", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Tanvi Desai", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Siddharth Bose", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Aisha Sheikh", program: "B.Tech CSE", semester: 3, section: "A" },
  { name: "Yash Agarwal", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Riya Sharma", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Aryan Bhat", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Kavya Nambiar", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Nikhil Jain", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Pooja Patel", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Manav Saxena", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Anjali Rane", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Harsh Vardhan", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Lakshmi Menon", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Omkar Kulkarni", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Sanya Kapadia", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Rehan Ali", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Divya Krishnan", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Varun Nadar", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Ira Chatterjee", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Aman Gill", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Neha Bansal", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Rudra Pandey", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Simran Kaur", program: "B.Tech CSE", semester: 3, section: "B" },
  { name: "Krishna Murthy", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Tara Fernandes", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Ayush Tiwari", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Myra DSouza", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Kunal Bhatt", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Zara Qureshi", program: "B.Tech ECE", semester: 5, section: "A", blocked: true },
  { name: "Parth Vyas", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Ridhi Sen", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Gaurav Naik", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Aditi Deshpande", program: "B.Tech ECE", semester: 5, section: "A" },
  { name: "Shaurya Rathore", program: "B.Tech IT", semester: 5, section: "A" },
  { name: "Naina Kohli", program: "B.Tech IT", semester: 5, section: "A" },
  { name: "Vikram Sinha", program: "B.Tech IT", semester: 5, section: "A" },
  { name: "Palak Arora", program: "B.Tech IT", semester: 5, section: "A" },
  { name: "Devansh Mishra", program: "B.Tech IT", semester: 5, section: "A" },
  { name: "Mahira Ansari", program: "B.Tech IT", semester: 5, section: "B" },
  { name: "Tejas Wagh", program: "B.Tech IT", semester: 5, section: "B" },
  { name: "Anushka Roy", program: "B.Tech IT", semester: 5, section: "B" },
  { name: "Farhan Sheikh", program: "B.Tech IT", semester: 5, section: "B" },
  { name: "Isha Bhardwaj", program: "B.Tech IT", semester: 5, section: "B" },
];

const branchCode = (program: string) =>
  program.includes("CSE") ? "CSE" : program.includes("ECE") ? "ECE" : "IT";

export const seedStudents: Student[] = roster.map((entry, i) => {
  const idx = i + 1;
  const code = branchCode(entry.program);
  return {
    id: `st-${String(idx).padStart(3, "0")}`,
    registrationNo: `23${code}${1000 + idx}`,
    name: entry.name,
    email: `${entry.name.toLowerCase().replace(/[^a-z]+/g, ".")}@northbridge.edu`,
    program: entry.program,
    semester: entry.semester,
    section: entry.section,
    status: entry.blocked ? "blocked" : "active",
    seat: `${entry.section}-${String(idx).padStart(2, "0")}`,
  };
});

const studentId = (n: number) => `st-${String(n).padStart(3, "0")}`;

// ---------------------------------------------------------------------------
// Labs and computers
// ---------------------------------------------------------------------------

export const seedLabs: Lab[] = [
  { id: "lab-a", name: "Advanced Computing Lab", building: "Newton Block · Level 2", capacity: 40, available: 34, invigilator: "Dr. Priya Raman", status: "occupied" },
  { id: "lab-b", name: "Systems Laboratory", building: "Turing Block · Level 1", capacity: 30, available: 28, invigilator: "Prof. M. Iqbal", status: "ready" },
  { id: "lab-c", name: "Networks Laboratory", building: "Turing Block · Level 3", capacity: 24, available: 0, invigilator: "Unassigned", status: "maintenance" },
];

// Deterministic connection pattern so monitoring/labs views stay stable.
function connectionFor(labId: string, pc: number): ConnectionStatus {
  if (labId === "lab-c") return "offline";
  if (labId === "lab-a") {
    if (pc % 13 === 0) return "offline";
    if (pc % 5 === 0) return "warning";
    return "online";
  }
  // lab-b: scheduled test, mostly ready/online with a couple of warnings.
  if (pc % 11 === 0) return "warning";
  return "online";
}

function buildLabComputers(labId: string, labNo: number, count: number, firstStudent: number, boundCount: number): Computer[] {
  return Array.from({ length: count }, (_, i) => {
    const pc = i + 1;
    const assigned = i < boundCount ? studentId(firstStudent + i) : undefined;
    return {
      id: `LAB${labNo}-PC-${String(pc).padStart(2, "0")}`,
      labId,
      index: pc,
      assignedStudentId: assigned,
      connection: assigned ? connectionFor(labId, pc) : "offline",
    };
  });
}

export const seedComputers: Computer[] = [
  // Students 1-40 seated in Advanced Computing Lab (Data Structures live exam).
  ...buildLabComputers("lab-a", 1, 40, 1, 40),
  // Students 41-60 seated in Systems Laboratory (Networks practice, scheduled).
  ...buildLabComputers("lab-b", 2, 30, 41, 20),
  // Networks Laboratory under maintenance, no assignments.
  ...buildLabComputers("lab-c", 3, 24, 0, 0),
];

const computerForStudent = (id: string) => seedComputers.find((c) => c.assignedStudentId === id);

// ---------------------------------------------------------------------------
// Questions (mixed types)
// ---------------------------------------------------------------------------

const dsQuestions: Question[] = [
  { id: "ds-q1", type: "mcq", prompt: "Which data structure follows the Last-In, First-Out principle?", options: ["Queue", "Stack", "Heap", "Graph"], correctOption: 1, marks: 2 },
  { id: "ds-q2", type: "mcq", prompt: "What is the average time complexity of search in a balanced binary search tree?", options: ["O(1)", "O(log n)", "O(n)", "O(n²)"], correctOption: 1, marks: 2 },
  { id: "ds-q3", type: "mcq", prompt: "Which traversal visits the root between the left and right subtrees?", options: ["Preorder", "Inorder", "Postorder", "Level order"], correctOption: 1, marks: 2 },
  { id: "ds-q4", type: "multiple", prompt: "Select every data structure that provides O(1) average-time insertion at one end.", options: ["Stack", "Hash table", "Sorted array", "Queue"], correctOptions: [0, 1, 3], marks: 3 },
  { id: "ds-q5", type: "multiple", prompt: "Which of the following are self-balancing binary search trees?", options: ["AVL tree", "Red-black tree", "Binary heap", "Splay tree"], correctOptions: [0, 1, 3], marks: 3 },
  { id: "ds-q6", type: "text", prompt: "Explain in one sentence why hashing can degrade to O(n) lookup time.", options: [], marks: 2 },
];

const osQuestions: Question[] = [
  { id: "os-q1", type: "mcq", prompt: "Which scheduling algorithm can cause starvation of long processes?", options: ["First-Come First-Served", "Shortest Job First", "Round Robin", "FIFO"], correctOption: 1, marks: 5 },
  { id: "os-q2", type: "mcq", prompt: "A deadlock requires all of the following conditions except which?", options: ["Mutual exclusion", "Hold and wait", "Preemption", "Circular wait"], correctOption: 2, marks: 5 },
  { id: "os-q3", type: "multiple", prompt: "Which mechanisms are used for inter-process communication?", options: ["Pipes", "Shared memory", "Message queues", "Page tables"], correctOptions: [0, 1, 2], marks: 5 },
  { id: "os-q4", type: "text", prompt: "Describe the difference between a process and a thread in one sentence.", options: [], marks: 5 },
];

const dbQuestions: Question[] = [
  { id: "db-q1", type: "mcq", prompt: "Which normal form removes transitive functional dependencies?", options: ["1NF", "2NF", "3NF", "BCNF"], correctOption: 2, marks: 10 },
  { id: "db-q2", type: "mcq", prompt: "Which SQL clause filters groups produced by GROUP BY?", options: ["WHERE", "HAVING", "ON", "ORDER BY"], correctOption: 1, marks: 10 },
  { id: "db-q3", type: "multiple", prompt: "Select the ACID properties of a database transaction.", options: ["Atomicity", "Consistency", "Isolation", "Durability"], correctOptions: [0, 1, 2, 3], marks: 20 },
  { id: "db-q4", type: "text", prompt: "State one advantage of a clustered index over a non-clustered index.", options: [], marks: 20 },
];

const cnQuestions: Question[] = [
  { id: "cn-q1", type: "mcq", prompt: "Which layer of the OSI model is responsible for routing?", options: ["Data link", "Network", "Transport", "Session"], correctOption: 1, marks: 2 },
  { id: "cn-q2", type: "mcq", prompt: "Which protocol guarantees ordered, reliable delivery?", options: ["UDP", "TCP", "ICMP", "ARP"], correctOption: 1, marks: 2 },
  { id: "cn-q3", type: "multiple", prompt: "Which addresses belong to private IPv4 ranges?", options: ["10.0.0.5", "192.168.1.10", "8.8.8.8", "172.16.4.2"], correctOptions: [0, 1, 3], marks: 3 },
  { id: "cn-q4", type: "text", prompt: "Explain the purpose of the TCP three-way handshake in one sentence.", options: [], marks: 3 },
];

const sumMarks = (qs: Question[]) => qs.reduce((s, q) => s + q.marks, 0);

// ---------------------------------------------------------------------------
// Tests
//
// Every timestamp is derived from the moment the demo state is created rather
// than a frozen calendar date, so "Today's examinations", the live countdown,
// and the audit trail stay coherent however long after authoring the app runs.
// ---------------------------------------------------------------------------

const MINUTES_PER_DAY = 1440;
const iso = (base: number, offsetMinutes: number) => new Date(base + offsetMinutes * 60_000).toISOString();

const dsRoster = Array.from({ length: 40 }, (_, i) => studentId(i + 1));
const cnRoster = Array.from({ length: 20 }, (_, i) => studentId(i + 41));

// The completed exam sits well in the past; results reference the same instant.
const dbmsScheduledOffset = -45 * MINUTES_PER_DAY;

function buildTests(now: number): Test[] {
  return [
  {
    id: "ds-midsem",
    title: "Data Structures Mid-Semester",
    code: "CSE-203-M1",
    course: "Data Structures & Algorithms",
    department: "Computer Science",
    description: "Mid-semester assessment covering linear structures, trees, and hashing.",
    durationMinutes: 45,
    totalMarks: sumMarks(dsQuestions),
    scheduledAt: iso(now, -30),
    status: "live",
    labId: "lab-a",
    assignedStudentIds: dsRoster,
    instructions: ["Answer all six questions.", "Do not refresh or close the examination window.", "Flagged questions can be revisited before submission."],
    questions: dsQuestions,
    config: { questionsPerStudent: 6, randomizeQuestions: false, randomizeOptions: false, allowNavigation: true, autoSubmitOnExpiry: true },
  },
  {
    id: "os-quiz-2",
    title: "Operating Systems Quiz II",
    code: "CSE-305-Q2",
    course: "Operating Systems",
    department: "Computer Science",
    description: "Short quiz on scheduling, deadlocks, and inter-process communication.",
    durationMinutes: 30,
    totalMarks: sumMarks(osQuestions),
    scheduledAt: iso(now, 2 * MINUTES_PER_DAY),
    status: "draft",
    labId: "lab-b",
    assignedStudentIds: cnRoster,
    instructions: ["Answer every question."],
    questions: osQuestions,
    config: { questionsPerStudent: 4, randomizeQuestions: true, randomizeOptions: true, allowNavigation: true, autoSubmitOnExpiry: true },
  },
  {
    id: "dbms-endsem",
    title: "Database Systems End-Semester",
    code: "CSE-302-E1",
    course: "Database Management Systems",
    department: "Computer Science",
    description: "End-semester examination covering normalization, SQL, and transactions.",
    durationMinutes: 90,
    totalMarks: sumMarks(dbQuestions),
    scheduledAt: iso(now, dbmsScheduledOffset),
    status: "completed",
    labId: "lab-a",
    assignedStudentIds: dsRoster,
    instructions: ["Answer all questions."],
    questions: dbQuestions,
    config: { questionsPerStudent: 4, randomizeQuestions: false, randomizeOptions: false, allowNavigation: true, autoSubmitOnExpiry: true },
  },
  {
    id: "networks-practice",
    title: "Computer Networks Practice Test",
    code: "CSE-307-P1",
    course: "Computer Networks",
    department: "Computer Science",
    description: "Monitored practice test on the OSI model, transport protocols, and addressing.",
    durationMinutes: 40,
    totalMarks: sumMarks(cnQuestions),
    scheduledAt: iso(now, 90),
    status: "scheduled",
    labId: "lab-b",
    assignedStudentIds: cnRoster,
    instructions: ["This is a monitored practice test."],
    questions: cnQuestions,
    config: { questionsPerStudent: 4, randomizeQuestions: true, randomizeOptions: false, allowNavigation: true, autoSubmitOnExpiry: true },
  },
  ];
}

// ---------------------------------------------------------------------------
// Live sessions for the Data Structures mid-semester exam
// ---------------------------------------------------------------------------

// Assign a per-student exam status pattern for the live exam.
function examStatusFor(index: number, connection: ConnectionStatus): StudentExamStatus {
  if (connection === "offline") return "not-ready";
  if (index % 9 === 0) return "submitted";
  if (index % 4 === 0) return "ready";
  return "in-progress";
}

function buildSessions(now: number): ExamSession[] {
  return dsRoster.map((sid, i) => {
    const computer = computerForStudent(sid);
    const connection: ConnectionStatus = computer?.connection ?? "offline";
    const examStatus = examStatusFor(i + 1, connection);
    const warnings = connection === "warning" ? 2 : connection === "offline" ? 1 : 0;

    const activity: ActivityEntry[] = [];
    if (connection !== "offline") {
      activity.push({ at: iso(now, -38), label: "Signed in to exam client", severity: "info" });
      activity.push({ at: iso(now, -35), label: "System readiness check passed", severity: "info" });
    }
    if (examStatus === "in-progress" || examStatus === "submitted") {
      activity.push({ at: iso(now, -30), label: "Exam started", severity: "info" });
    }
    if (connection === "warning") {
      activity.push({ at: iso(now, -12), label: "Focus lost — switched away from window", severity: "warning" });
      activity.push({ at: iso(now, -11), label: "Returned to exam window", severity: "info" });
    }
    if (connection === "offline") {
      activity.push({ at: iso(now, -6), label: "Connection lost", severity: "critical" });
    }
    if (examStatus === "submitted") {
      activity.push({ at: iso(now, -3), label: "Exam submitted", severity: "info" });
    }

    return {
      testId: "ds-midsem",
      studentId: sid,
      computerId: computer?.id ?? `LAB1-PC-${String(i + 1).padStart(2, "0")}`,
      connection,
      examStatus,
      loginAt: connection === "offline" ? undefined : iso(now, -38),
      examStartedAt: examStatus === "in-progress" || examStatus === "submitted" ? iso(now, -30) : undefined,
      lastHeartbeatAt:
        connection === "offline" ? iso(now, -6) : connection === "warning" ? iso(now, -1) : iso(now, 0),
      warnings,
      activity,
    };
  });
}

// ---------------------------------------------------------------------------
// Results (completed Database Systems end-semester)
// ---------------------------------------------------------------------------

const dbTotal = sumMarks(dbQuestions);
// Raw marks awarded out of `dbTotal`. Clamped below so a seed edit can never
// produce a percentage above 100 in the results table.
const dbScores = [48, 60, 35, 42, 39, 45, 28, 51, 47, 32, 40, 53, 37, 44, 49, 30, 34, 52, 41, 38, 46, 29, 43, 36, 50, 33, 58, 31];

function buildResults(now: number): Result[] {
  return dbScores.map((score, i) => ({
    id: `res-${String(i + 1).padStart(3, "0")}`,
    testId: "dbms-endsem",
    studentId: studentId(i + 1),
    score: Math.min(score, dbTotal),
    total: dbTotal,
    // Submitted 70–90 minutes into the 90-minute completed examination.
    submittedAt: iso(now, dbmsScheduledOffset + 70 + (i % 20)),
    mode: i % 7 === 0 ? "automatic" : "manual",
  }));
}

// ---------------------------------------------------------------------------
// Audit events
// ---------------------------------------------------------------------------

function buildAudits(now: number): AuditEvent[] {
  return [
    { id: "audit-1", at: iso(now, -3), actor: "System", action: "Exam submitted", detail: "Aditya Rao submitted Data Structures Mid-Semester from LAB1-PC-09.", studentId: "st-009", computerId: "LAB1-PC-09", category: "exam", severity: "info" },
    { id: "audit-2", at: iso(now, -6), actor: "System", action: "Connection lost", detail: "LAB1-PC-13 dropped its heartbeat during the live examination.", studentId: "st-013", computerId: "LAB1-PC-13", category: "connection", severity: "critical" },
    { id: "audit-3", at: iso(now, -11), actor: "System", action: "Focus lost", detail: "Ishita Gupta switched away from the exam window on LAB1-PC-10.", studentId: "st-010", computerId: "LAB1-PC-10", category: "exam", severity: "warning" },
    { id: "audit-4", at: iso(now, -30), actor: "Dr. Priya Raman", action: "Exam started", detail: "Data Structures Mid-Semester went live for 40 assigned candidates.", category: "exam", severity: "info" },
    { id: "audit-5", at: iso(now, -35), actor: "System", action: "Device health check", detail: "34 of 40 assigned workstations in Advanced Computing Lab reported ready.", category: "system", severity: "info" },
    { id: "audit-6", at: iso(now, -12), actor: "System", action: "Warning threshold reached", detail: "LAB1-PC-05 recorded a second invigilation warning.", studentId: "st-005", computerId: "LAB1-PC-05", category: "connection", severity: "warning" },
    { id: "audit-7", at: iso(now, -220), actor: "Exam Cell · Anita Rao", action: "Roster verified", detail: "40 candidates matched for CSE-203-M1 in Advanced Computing Lab.", category: "system", severity: "info" },
    { id: "audit-8", at: iso(now, -300), actor: "System", action: "Lab capacity warning", detail: "Networks Laboratory marked unavailable due to maintenance.", computerId: "LAB3-PC-01", category: "system", severity: "warning" },
  ];
}

// ---------------------------------------------------------------------------
// Seed state factory
// ---------------------------------------------------------------------------

export function createSeedState(): ExamState {
  const now = Date.now();
  const nowIso = new Date(now).toISOString();
  const tests = buildTests(now).map((test) =>
    test.id === "ds-midsem" ? { ...test, endsAt: iso(now, test.durationMinutes - 30) } : test,
  );
  // The live exam ships a rich hand-authored timeline; every other non-draft
  // test is seated from its roster so its monitor and readiness views populate.
  const sessions = buildSessions(now);
  for (const test of tests) {
    if (test.status === "scheduled" || test.status === "live") {
      sessions.push(...missingSessions(test, seedComputers, sessions, nowIso));
    }
  }
  return {
    version: 2,
    tests,
    students: seedStudents,
    labs: seedLabs,
    computers: seedComputers,
    sessions,
    results: buildResults(now),
    audits: buildAudits(now),
    submissions: [],
    answers: {},
    flags: {},
    toasts: [],
    mockResultMode: false,
  };
}
