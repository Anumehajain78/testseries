"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useExam } from "@/app/providers";
import { homeFor, permits, type Audience } from "@/lib/access";

// ---------------------------------------------------------------------------
// Keeping people in their own half of the application
//
// A candidate who typed, bookmarked or was sent an /admin URL used to get the
// administration console: the sidebar, the assessment list, and a footer
// naming them "Exam Controller". Nothing leaked — every one of those screens
// asks the server for its data and the server refuses a candidate — but the
// screen said otherwise, and a screen that looks like it worked is its own
// kind of wrong. An invigilator glancing at a candidate's monitor should not
// have to work out whether what they are seeing is real.
//
// This is presentation, not protection. The guard that matters is on the API,
// where it cannot be edited away by whoever is holding the keyboard; this one
// only makes the browser agree with it.
// ---------------------------------------------------------------------------

export function RequireRole({ audience, children }: { audience: Audience; children: React.ReactNode }) {
  const { currentUser } = useExam();
  const router = useRouter();
  const role = currentUser?.role;
  const allowed = permits(audience, role);

  useEffect(() => {
    // Replace rather than push: the page they could not use should not be
    // sitting in their history for the back button to return them to.
    if (!allowed && role) router.replace(homeFor(role));
  }, [allowed, role, router]);

  // Rendered instead of the children, and deliberately outside the shell in
  // each layout, so the console's chrome never appears for a moment before
  // the redirect lands.
  if (!allowed) {
    return (
      <div className="loading-state">
        <span className="spinner" />
        <p>
          {!role
            ? "Checking your account…"
            : role === "STUDENT"
              ? "Taking you to your examination portal…"
              : "Taking you to the examination console…"}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
