import { describe, expect, it } from "vitest";
import { checkLabs, labVerdict } from "./health";
import type { Computer, ConnectionStatus, Lab } from "./types";

const lab = (id: string, name = "Lab One"): Lab =>
  ({ id, name, building: "Block A", status: "available", capacity: 40 } as unknown as Lab);

const pc = (
  id: string,
  labId: string,
  connection: ConnectionStatus,
  over: Partial<Computer> = {},
): Computer => ({
  id,
  labId,
  index: 1,
  connection,
  enrolledAt: "2026-09-01T09:00:00Z",
  lastSeenAt: "2026-09-09T09:00:00Z",
  ...over,
});

const AT = "2026-09-09T09:05:00Z";

describe("checkLabs", () => {
  it("counts a healthy lab as fully online", () => {
    const report = checkLabs([lab("l1")], [pc("a", "l1", "online"), pc("b", "l1", "online")], AT);
    expect(report.labs[0]).toMatchObject({ total: 2, online: 2, offline: 0 });
    expect(report.unusable).toBe(0);
  });

  it("separates a machine that never enrolled from one that has gone quiet", () => {
    // They need different people: one needs the lab client run on it, the
    // other needs someone to look at a machine that was working.
    const report = checkLabs([lab("l1")], [
      pc("a", "l1", "offline", { enrolledAt: null, lastSeenAt: null }),
      pc("b", "l1", "offline"),
      pc("c", "l1", "online"),
    ], AT);
    expect(report.labs[0].neverEnrolled).toBe(1);
    expect(report.labs[0].offline).toBe(2);
    expect(report.labs[0].neverSeen).toBe(0);
    // Only the one that used to report counts as having gone quiet.
    expect(report.labs[0].quiet).toBe(1);
  });

  it("counts an enrolled machine that has never reported", () => {
    const report = checkLabs([lab("l1")], [pc("a", "l1", "offline", { lastSeenAt: null })], AT);
    expect(report.labs[0].neverSeen).toBe(1);
    expect(report.labs[0].neverEnrolled).toBe(0);
    // It has not "gone quiet" — it never spoke.
    expect(report.labs[0].quiet).toBe(0);
  });

  it("reports the oldest heartbeat it has, ignoring machines that never sent one", () => {
    const report = checkLabs([lab("l1")], [
      pc("a", "l1", "online", { lastSeenAt: "2026-09-09T08:00:00Z" }),
      pc("b", "l1", "online", { lastSeenAt: "2026-09-09T09:00:00Z" }),
      pc("c", "l1", "offline", { lastSeenAt: null }),
    ], AT);
    expect(report.labs[0].oldestSeenAt).toBe("2026-09-09T08:00:00Z");
  });

  it("counts only the machines in its own lab", () => {
    const report = checkLabs(
      [lab("l1"), lab("l2", "Lab Two")],
      [pc("a", "l1", "online"), pc("b", "l2", "offline")],
      AT,
    );
    expect(report.labs[0].total).toBe(1);
    expect(report.labs[1].total).toBe(1);
    expect(report.labs[1].offline).toBe(1);
  });

  it("counts unusable workstations across every lab", () => {
    const report = checkLabs(
      [lab("l1"), lab("l2", "Lab Two")],
      [
        pc("a", "l1", "offline"),
        pc("b", "l2", "offline", { enrolledAt: null, lastSeenAt: null }),
        pc("c", "l2", "online"),
      ],
      AT,
    );
    // Two machines, not three reasons: the unenrolled one is offline as well,
    // and counting both reasons would report it twice.
    expect(report.unusable).toBe(2);
  });
});

describe("labVerdict", () => {
  const row = (over: Partial<ReturnType<typeof checkLabs>["labs"][number]>) => ({
    lab: lab("l1"), total: 4, online: 4, warning: 0, offline: 0,
    neverEnrolled: 0, neverSeen: 0, quiet: 0, unusable: 0, oldestSeenAt: null, ...over,
  });

  it("is ok when every machine is online", () => {
    expect(labVerdict(row({}))).toBe("ok");
  });

  it("wants attention when any machine is slow or quiet", () => {
    expect(labVerdict(row({ online: 3, warning: 1 }))).toBe("attention");
    expect(labVerdict(row({ online: 3, offline: 1 }))).toBe("attention");
    expect(labVerdict(row({ neverEnrolled: 1 }))).toBe("attention");
  });

  it("calls a lab with nothing online unusable", () => {
    expect(labVerdict(row({ online: 0, offline: 4 }))).toBe("unusable");
  });

  it("does not give an empty lab a clean bill", () => {
    // Zero of zero offline is not health, it is a room with no computers in it.
    expect(labVerdict(row({ total: 0, online: 0 }))).toBe("unusable");
  });
});
