import type { Computer, Lab } from "./types";

// ---------------------------------------------------------------------------
// Lab health
//
// The server cannot reach out to a workstation — machines report in, and their
// liveness is derived from the last heartbeat received. So a health check is a
// reading of what has arrived, not a ping, and it says so.
//
// The three failures are kept apart because they need different people:
//   never enrolled — nobody has run the lab client on that machine
//   never seen     — enrolled, but it has not reported once
//   quiet          — it was reporting and has stopped
// Collapsing them into "offline" would send a technician to the wrong room.
// ---------------------------------------------------------------------------

export interface LabHealth {
  lab: Lab;
  total: number;
  online: number;
  warning: number;
  offline: number;
  neverEnrolled: number;
  neverSeen: number;
  /** Offline machines that *have* reported before. Kept apart from neverSeen
   *  so the same workstation is not described twice — "gone quiet" and "never
   *  reported" are different faults and reading both against one machine tells
   *  a technician nothing. */
  quiet: number;
  /** Machines that cannot seat a candidate: quiet or never enrolled. Counted
   *  as machines, not as reasons — an unenrolled workstation is offline too,
   *  and adding the two counts together reports it twice. */
  unusable: number;
  /** Oldest heartbeat among machines that have reported at least once. */
  oldestSeenAt: string | null;
}

export interface HealthReport {
  checkedAt: string;
  labs: LabHealth[];
  /** Workstations that cannot currently seat a candidate. */
  unusable: number;
}

export function checkLabs(labs: Lab[], computers: Computer[], checkedAt: string): HealthReport {
  const rows = labs.map((lab) => {
    const own = computers.filter((computer) => computer.labId === lab.id);
    const seen = own
      .map((computer) => computer.lastSeenAt)
      .filter((at): at is string => Boolean(at))
      .sort();
    return {
      lab,
      total: own.length,
      online: own.filter((c) => c.connection === "online").length,
      warning: own.filter((c) => c.connection === "warning").length,
      offline: own.filter((c) => c.connection === "offline").length,
      neverEnrolled: own.filter((c) => !c.enrolledAt).length,
      neverSeen: own.filter((c) => c.enrolledAt && !c.lastSeenAt).length,
      quiet: own.filter((c) => c.connection === "offline" && c.lastSeenAt).length,
      unusable: own.filter((c) => c.connection === "offline" || !c.enrolledAt).length,
      oldestSeenAt: seen[0] ?? null,
    };
  });

  return {
    checkedAt,
    labs: rows,
    unusable: rows.reduce((sum, row) => sum + row.unusable, 0),
  };
}

/** A lab with no workstations at all is not healthy — it is unusable, and an
 *  empty room reporting "0 offline" would read as a clean bill. */
export const labVerdict = (row: LabHealth): "ok" | "attention" | "unusable" => {
  if (row.total === 0 || row.online === 0) return "unusable";
  if (row.offline > 0 || row.warning > 0 || row.neverEnrolled > 0 || row.neverSeen > 0) return "attention";
  return "ok";
};
