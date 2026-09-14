import { RequireRole } from "@/components/require-role";
import { StudentShell } from "@/components/shells";

// Both directions. Staff opening a candidate's portal would otherwise see a
// waiting room for an examination they are not sitting.
export default function Layout({ children }: { children: React.ReactNode }) {
  return <RequireRole audience="candidate"><StudentShell>{children}</StudentShell></RequireRole>;
}
