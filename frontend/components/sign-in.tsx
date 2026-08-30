"use client";

import { useState, type FormEvent } from "react";
import { ApiError, signIn } from "@/lib/api";
import { Icon } from "./icons";

// ---------------------------------------------------------------------------
// Sign-in gate
//
// Shown only in live mode, and only while there is no access token. The
// examination screens are read-only against the server at this step, so this
// exists to obtain a credential rather than to be the finished authentication
// experience — route protection, refresh rotation and role-aware redirects
// come with the write cutover.
// ---------------------------------------------------------------------------

export function SignInGate({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim().toLowerCase(), password);
      onSignedIn();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not reach the examination server. Check that it is running.",
      );
      setBusy(false);
    }
  };

  return (
    <div className="signin-page">
      <form className="signin-card" onSubmit={submit}>
        <span className="brand-mark"><Icon name="book" size={22} /></span>
        <h1>Sign in</h1>
        <p>Use your institutional credentials to reach the examination console.</p>

        <label className="field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="anita.rao@northbridge.edu"
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {error && <p className="field-error" role="alert">{error}</p>}

        <button className="btn btn-primary" type="submit" disabled={busy}>
          <span>{busy ? "Signing in…" : "Sign in"}</span>
        </button>
      </form>
    </div>
  );
}

export function ConnectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="signin-page">
      <div className="signin-card">
        <span className="brand-mark warn"><Icon name="alert" size={22} /></span>
        <h1>Cannot reach the server</h1>
        <p>{message}</p>
        <button className="btn btn-primary" type="button" onClick={onRetry}><span>Try again</span></button>
      </div>
    </div>
  );
}
