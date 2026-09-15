"use client";

import { useState, type FormEvent } from "react";
import { ApiError, directory, type ImportSummaryDto, type NewStudentDto, type PasswordResetDto } from "@/lib/api";
import { sessionsEndedNote } from "@/lib/passwords";
import type { Student, Test } from "@/lib/types";
import { Icon } from "./icons";
import { Badge, Button, Field, Modal, Select } from "./ui";

// ---------------------------------------------------------------------------
// Adding candidates
//
// Until this existed the register could only come from the seed file, which
// made the platform undeployable: a college cannot use an examination system
// it is unable to put its own students into.
//
// Passwords are generated and shown once. Sixty cannot be invented by hand,
// and the obvious shortcut — using the registration number — would let any
// candidate sign in as any other.
// ---------------------------------------------------------------------------

const PROGRAMS = ["B.Tech CSE", "B.Tech ECE", "B.Tech IT"];

const SAMPLE = "registration_no,full_name,email,program,semester,section";

/** Passwords the administrator has to pass on before leaving the screen.
 *
 *  `heading` exists because a reset is the same moment as an addition — one
 *  password, readable once, that has to leave the screen with the person
 *  reading it — but "1 candidate added" would be a lie about what happened. */
function Credentials({ created, heading }: { created: NewStudentDto[]; heading?: string }) {
  const [copied, setCopied] = useState(false);
  if (!created.length) return null;

  const asText = created
    .map((row) => `${row.student.registrationNo}\t${row.student.fullName}\t${row.temporaryPassword}`)
    .join("\n");

  return (
    <div className="credentials">
      <div className="credentials-head">
        <div>
          <strong>{heading ?? `${created.length} ${created.length === 1 ? "candidate" : "candidates"} added`}</strong>
          {/* Said plainly, because closing this dialog destroys them. */}
          <small>These passwords are shown once. Copy them before closing.</small>
        </div>
        <Button
          type="button"
          tone="secondary"
          icon="file"
          onClick={() => {
            void navigator.clipboard?.writeText(asText).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy all"}
        </Button>
      </div>
      <div className="credentials-list">
        {created.map((row) => (
          <div key={row.student.id}>
            <span>{row.student.registrationNo}</span>
            <span>{row.student.fullName}</span>
            <code>{row.temporaryPassword}</code>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AddStudentDialog({ open, onClose, onAdded }: {
  open: boolean;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [form, setForm] = useState({
    registrationNo: "", fullName: "", email: "",
    program: PROGRAMS[0], semester: 3, section: "A",
  });
  const [created, setCreated] = useState<NewStudentDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      setCreated(await directory.createStudent(form));
      onAdded();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The candidate could not be added.");
    } finally {
      setSaving(false);
    }
  };

  const finish = () => {
    setCreated(null);
    setForm({ registrationNo: "", fullName: "", email: "", program: PROGRAMS[0], semester: 3, section: "A" });
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={finish}
      title={created ? "Candidate added" : "Add a candidate"}
      mark={created ? "check" : "users"}
      description={created ? undefined : "They can sign in as soon as you give them the password."}
      actions={created
        ? <Button onClick={finish}>Done</Button>
        : <>
            <Button tone="secondary" onClick={finish} type="button">Cancel</Button>
            <Button icon="check" onClick={submit} disabled={saving} type="button">
              {saving ? "Adding…" : "Add candidate"}
            </Button>
          </>}
    >
      {created ? <Credentials created={[created]} /> : (
        <form className="roster-form" onSubmit={submit}>
          <Field label="Registration number" value={form.registrationNo} required
            onChange={(e) => set({ registrationNo: e.target.value })} placeholder="23CSE1061" />
          <Field label="Full name" value={form.fullName} required
            onChange={(e) => set({ fullName: e.target.value })} placeholder="Priya Sharma" />
          <Field label="Email" type="email" value={form.email} required
            onChange={(e) => set({ email: e.target.value })} placeholder="priya.sharma@northbridge.edu" />
          <Select label="Programme" value={form.program} onChange={(e) => set({ program: e.target.value })}>
            {PROGRAMS.map((program) => <option key={program}>{program}</option>)}
          </Select>
          <Field label="Semester" type="number" min={1} max={12} value={form.semester}
            onChange={(e) => set({ semester: Number(e.target.value) })} />
          <Field label="Section" value={form.section} required
            onChange={(e) => set({ section: e.target.value })} />
          {error && <p className="field-error" role="alert">{error}</p>}
        </form>
      )}
    </Modal>
  );
}

export function ImportRosterDialog({ open, onClose, onImported }: {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}) {
  const [csv, setCsv] = useState("");
  const [summary, setSummary] = useState<ImportSummaryDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      setSummary(await directory.importRoster(csv));
      onImported();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The file could not be read.");
    } finally {
      setBusy(false);
    }
  };

  const finish = () => {
    setSummary(null);
    setCsv("");
    setError(null);
    onClose();
  };

  const failed = summary?.failed ?? [];

  return (
    <Modal
      open={open}
      onClose={finish}
      title={summary ? "Import finished" : "Import a roster"}
      mark={summary ? "check" : "file"}
      description={summary ? undefined : "Paste a spreadsheet export. Anything that cannot be read is reported row by row."}
      actions={summary
        ? <Button onClick={finish}>Done</Button>
        : <>
            <Button tone="secondary" onClick={finish} type="button">Cancel</Button>
            <Button icon="check" onClick={submit} disabled={busy || !csv.trim()} type="button">
              {busy ? "Importing…" : "Import"}
            </Button>
          </>}
    >
      {summary ? (
        <div className="import-result">
          <Credentials created={summary.created ?? []} />
          {failed.length > 0 && (
            <div className="import-failed">
              <strong>
                <Icon name="alert" size={16}/> {failed.length} row
                {failed.length === 1 ? "" : "s"} could not be added
              </strong>
              {/* Named individually so the file can be corrected, rather than
                  a count that leaves the administrator guessing. */}
              <ul>
                {failed.map((row) => (
                  <li key={`${row.line}-${row.registrationNo}`}>
                    <span>Line {row.line}</span>
                    <span>{row.registrationNo || "—"}</span>
                    <span>{row.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!summary.created?.length && !failed.length && (
            <p className="field-hint">The file had no rows in it.</p>
          )}
        </div>
      ) : (
        <div className="import-form">
          <label className="field">
            <span>Roster</span>
            <textarea
              rows={9}
              value={csv}
              onChange={(event) => setCsv(event.target.value)}
              placeholder={`${SAMPLE}\n23CSE1061,Priya Sharma,priya.sharma@northbridge.edu,B.Tech CSE,3,A`}
              spellCheck={false}
            />
          </label>
          <p className="field-hint">
            Needs these columns: <code>{SAMPLE}</code>
          </p>
          <label className="field">
            <span>Or choose a file</span>
            <input
              type="file"
              accept=".csv,text/csv,text/plain"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void file.text().then(setCsv);
              }}
            />
          </label>
          {csv.trim() && <Badge tone="info">{csv.trim().split("\n").length - 1} rows ready</Badge>}
          {error && <p className="field-error" role="alert">{error}</p>}
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Resetting a candidate's password
//
// The exam-morning job: somebody is at the desk without their slip and cannot
// sit the paper. There is no self-service reset — nothing is emailed — so the
// exam cell issuing a new password over the counter is the only route back in,
// and it has to be quick enough to use with a queue forming.
//
// Quick, but not accidental. It invalidates the password the candidate is
// holding and ends every session opened with it, so the cost is spelled out
// before the button rather than discovered after it.
// ---------------------------------------------------------------------------

function resetRefusal(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.status === 403) {
      return "Only the exam cell can reset a candidate's password. Ask them to do it from their own account.";
    }
    if (cause.status === 404) {
      return "That candidate is no longer on the register. Reload this screen before trying again.";
    }
    return cause.message;
  }
  return "The password could not be reset. The examination server did not answer.";
}

export function ResetPasswordDialog({ student, sitting, onClose, onReset }: {
  /** The candidate to reset, or null when the dialog is closed. */
  student: Student | null;
  /** The examination they are part-way through, if the console knows of one. */
  sitting?: Test;
  onClose: () => void;
  onReset: () => void;
}) {
  const [issued, setIssued] = useState<PasswordResetDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reset = async () => {
    if (!student) return;
    setBusy(true);
    setError(null);
    try {
      setIssued(await directory.resetStudentPassword(student.id));
      // The candidate's sessions have just ended, so the roster and monitor on
      // screen are now describing a hall that has changed.
      onReset();
    } catch (cause) {
      setError(resetRefusal(cause));
    } finally {
      setBusy(false);
    }
  };

  const finish = () => {
    setIssued(null);
    setError(null);
    onClose();
  };

  return (
    <Modal
      open={Boolean(student)}
      onClose={() => { if (!busy) finish(); }}
      title={issued
        ? "New password issued"
        : `Reset the password for ${student?.name ?? "this candidate"}?`}
      mark={issued ? "check" : "alert"}
      description={issued
        ? undefined
        : "The password they are holding stops working the moment you confirm, and cannot be recovered — this screen is the only place the new one is readable."}
      actions={issued
        ? <Button onClick={finish}>Done</Button>
        : <>
            <Button tone="secondary" type="button" onClick={finish} disabled={busy}>Cancel</Button>
            <Button tone="danger" type="button" onClick={() => { void reset(); }} disabled={busy}>
              {busy ? "Resetting…" : "Reset and sign them out"}
            </Button>
          </>}
    >
      {issued ? (
        <div className="import-result">
          <Credentials created={[issued]} heading={`New password for ${issued.student.fullName}`}/>
          {/* The count, not an assertion that sessions were closed. Four live
              sign-ins going at once is either exactly what was meant or the
              first sign that the wrong row was picked, and only the number
              tells the two apart. */}
          <div className="password-done">
            <p>{sessionsEndedNote(issued.sessionsEnded, "theirs")}</p>
            <p className="password-note">
              Hand them this password and they can sign in again straight away; nobody — including
              the exam cell — can read it after this dialog closes.
            </p>
          </div>
        </div>
      ) : (
        <div className="import-result">
          <div className="launch-summary">
            <strong>{student?.name}</strong>
            <span>{student?.registrationNo} · {student?.email}</span>
          </div>
          {/* Said before the confirmation, not in a toast afterwards. An exam
              cell that learns this after pressing the button has already put a
              candidate out of a paper they were half-way through. */}
          <p className="reset-warning">
            <Icon name="alert" size={17}/>
            <span>
              <strong>This ends every session the candidate has, on every device.</strong>{" "}
              {sitting
                ? `They are sitting ${sitting.title} (${sitting.code}) right now, and this signs them out of it. The answers they have saved stay saved, but they cannot get back into the paper until you have handed them the new password — and the exam clock keeps running while that happens.`
                : "If they are part-way through an examination on another screen, this signs them out of it. Answers they have saved stay saved, but they cannot get back into the paper until you have handed them the new password, and the exam clock keeps running while that happens."}
            </span>
          </p>
          {error && <p className="field-error" role="alert">{error}</p>}
        </div>
      )}
    </Modal>
  );
}
