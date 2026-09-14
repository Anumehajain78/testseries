// ---------------------------------------------------------------------------
// Which half of the application someone belongs in
//
// Policy, kept away from the component that enforces it so it can be read and
// tested on its own. The component decides what to render; this decides who is
// allowed to see it.
//
// Presentation, not protection. The guard that matters is on the API, where it
// cannot be edited away by whoever is holding the keyboard.
// ---------------------------------------------------------------------------

export type Audience = "staff" | "candidate";

/** Where someone of this role belongs, when they are somewhere they do not. */
export const homeFor = (role: string | undefined): string =>
  role === "STUDENT" ? "/student" : "/admin";

/** Whether this role may see this half of the application.
 *
 * Unknown roles are refused. A role added on the server reaches this before
 * anybody teaches the frontend about it, and refusing is the safe direction to
 * be wrong in.
 */
export function permits(audience: Audience, role: string | undefined): boolean {
  if (!role) return false;
  return audience === "staff" ? role === "ADMIN" || role === "FACULTY" : role === "STUDENT";
}
