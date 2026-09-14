// ---------------------------------------------------------------------------
// Telling the lab client which paper is on screen
//
// The desktop client is the only thing that can see a candidate switch away
// from the examination — a browser cannot — and it reports that to the server
// as a session event. Which means it needs a session id, and it has no way to
// ask for one: `/me/sessions` needs a candidate's token, and a workstation
// authenticates as a machine. The machine and the candidate are deliberately
// separate subjects, and collapsing them so the client could look this up
// would be a far worse trade than passing one identifier.
//
// So the page hands it over. It already knows the session id — it is answering
// that paper — and the desktop shell polls this global for it. Without this
// the client observes everything and can file none of it: focus events queue
// on the workstation and are silently dropped.
//
// Written to `window` rather than sent anywhere. The desktop shell is the only
// reader, and in an ordinary browser this is an unused property.
// ---------------------------------------------------------------------------

/** The name the desktop client's injected script reads. Changing it here means
 *  changing it in `desktop/src-tauri/src/lockdown.rs`, and the consequence of
 *  the two drifting is invigilation that quietly stops working. */
const GLOBAL = "__EXAM_SESSION_ID__";

type WindowWithSession = Window & { [GLOBAL]?: string };

/** Announce the paper on screen, or clear it when there is none.
 *
 * Cleared on the way out as well as set on the way in: a stale id would have
 * the client filing a candidate's focus events against a paper they have
 * already submitted.
 */
export function announceSession(sessionId: string | null): void {
  if (typeof window === "undefined") return;
  const target = window as WindowWithSession;
  if (sessionId) target[GLOBAL] = sessionId;
  else delete target[GLOBAL];
}
