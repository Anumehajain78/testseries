"use client";

import { useState, type FormEvent } from "react";
import { ApiError, changePassword, type PasswordChangedDto } from "@/lib/api";
import { MIN_PASSWORD_LENGTH, SIGN_IN_REFUSAL, checkNewPassword, sessionsEndedNote } from "@/lib/passwords";
import { useExam } from "@/app/providers";
import { Icon } from "./icons";
import { Button, Field, Modal } from "./ui";

// ---------------------------------------------------------------------------
// Changing your own password
//
// For everyone who signs in — the exam cell, faculty, and candidates holding a
// password somebody at a counter read out to them. That last case is the whole
// reason this exists: a temporary password has been spoken aloud, written on a
// slip and handed over, and until its holder can replace it the only person
// who can is the exam cell.
//
// It is the same screen in both shells, because a candidate changing their
// password and an administrator changing theirs are the same act with the same
// consequence, and two versions of it would drift.
// ---------------------------------------------------------------------------

function refusal(cause: unknown): string {
  if (cause instanceof ApiError) {
    // Deliberately the sentence the sign-in screen uses. A refusal that said
    // "your current password is wrong" would confirm to whoever is at the
    // keyboard that the new password they chose was fine — which tells someone
    // who is not the account holder that they are one guess from being in.
    if (cause.status === 401) return SIGN_IN_REFUSAL;
    if (cause.status === 422) return cause.message;
    return `Your password could not be changed. The examination server answered ${cause.status}.`;
  }
  return "Your password could not be changed. The examination server did not answer.";
}

export function ChangePasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { signOut } = useExam();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState<PasswordChangedDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const problem = checkNewPassword(current, next, confirm);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setDone(await changePassword(current, next));
    } catch (cause) {
      setError(refusal(cause));
    } finally {
      setBusy(false);
    }
  };

  const cancel = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    setError(null);
    onClose();
  };

  // The change ended this session along with the others, so the credential in
  // this browser is already dead. Staying here would leave somebody clicking
  // around a console whose every request now fails; signing out puts the
  // sign-in form in front of them instead, which is what they need next.
  const leave = () => {
    setDone(null);
    setCurrent("");
    setNext("");
    setConfirm("");
    onClose();
    signOut();
  };

  return (
    <Modal
      open={open}
      onClose={() => { if (busy) return; if (done) leave(); else cancel(); }}
      title={done ? "Password changed" : "Change your password"}
      mark={done ? "check" : "shield"}
      description={done
        ? undefined
        : "Changing it signs you out everywhere, including this screen. You will need to sign in again straight afterwards."}
      actions={done
        ? <Button icon="logout" onClick={leave}>Sign in again</Button>
        : <>
            <Button tone="secondary" type="button" onClick={cancel} disabled={busy}>Cancel</Button>
            <Button icon="check" type="button" onClick={submit} disabled={busy}>
              {busy ? "Changing…" : "Change password"}
            </Button>
          </>}
    >
      {done ? (
        <div className="password-done">
          <p>{sessionsEndedNote(done.sessionsEnded, "yours")}</p>
          <p className="password-note">
            Sign in again with the new password. If you are on a shared lab machine, do that
            somewhere the screen is not being read over your shoulder.
          </p>
        </div>
      ) : (
        <form className="roster-form" onSubmit={submit}>
          <Field
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <Field
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={next}
            onChange={(event) => setNext(event.target.value)}
            // Stated up front rather than discovered by being refused: the
            // rule is short enough to print, and a person who reads it first
            // never meets the error at all.
            hint={`At least ${MIN_PASSWORD_LENGTH} characters, and not the one you are using now.`}
          />
          <Field
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
          <p className="password-warning">
            <Icon name="alert" size={16}/>
            <span>
              Every device signed in as you is signed out — this one included. Do not do this
              part-way through an examination you are sitting.
            </span>
          </p>
          {error && <p className="field-error" role="alert">{error}</p>}
        </form>
      )}
    </Modal>
  );
}

/**
 * The control that opens it, so both shells label it the same way.
 *
 * Only the button. The dialog goes at the root of each shell rather than
 * beside this, because the admin sidebar is `translateX`ed off-canvas on a
 * narrow screen — and a transformed ancestor becomes the containing block for
 * everything fixed inside it, which would slide the whole dialog off the side
 * of the screen with it.
 */
export function ChangePasswordButton({ onClick, size = 17 }: { onClick: () => void; size?: number }) {
  return (
    <button
      className="icon-button"
      type="button"
      onClick={onClick}
      title="Change your password"
      aria-label="Change your password"
    >
      <Icon name="reset" size={size}/>
    </button>
  );
}
