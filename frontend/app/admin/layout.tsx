import { RequireRole } from "@/components/require-role";
import { AdminShell } from "@/components/shells";

// The guard sits outside the shell on purpose: inside it, a candidate would
// see the console's sidebar and topbar for a moment before being sent away.
export default function Layout({ children }: { children: React.ReactNode }) {
  return <RequireRole audience="staff"><AdminShell>{children}</AdminShell></RequireRole>;
}
