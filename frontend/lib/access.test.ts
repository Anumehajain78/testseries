import { describe, expect, it } from "vitest";
import { homeFor, permits } from "./access";

// A candidate reaching the administration console saw the sidebar, the
// assessment list, and a footer calling them "Exam Controller". The server
// refused every request behind it, so nothing leaked — but the screen said
// otherwise, and an invigilator glancing at a monitor should not have to work
// out whether what they are seeing is real.

describe("who may see the administration console", () => {
  it("admits an administrator", () => {
    expect(permits("staff", "ADMIN")).toBe(true);
  });

  it("admits a teacher", () => {
    expect(permits("staff", "FACULTY")).toBe(true);
  });

  it("turns a candidate away", () => {
    expect(permits("staff", "STUDENT")).toBe(false);
  });

  it("turns away a role it has never heard of", () => {
    // A role added on the server reaches this before anyone teaches the
    // frontend about it. Refusing is the safe direction to be wrong in.
    expect(permits("staff", "INVIGILATOR")).toBe(false);
  });

  it("turns away nobody at all", () => {
    expect(permits("staff", undefined)).toBe(false);
  });
});

describe("who may see the candidate portal", () => {
  it("admits a candidate", () => {
    expect(permits("candidate", "STUDENT")).toBe(true);
  });

  it("turns staff away too", () => {
    // Both directions: a teacher opening a candidate's portal would see a
    // waiting room for an examination they are not sitting.
    expect(permits("candidate", "ADMIN")).toBe(false);
    expect(permits("candidate", "FACULTY")).toBe(false);
  });
});

describe("where somebody is sent instead", () => {
  it("sends a candidate to their own portal", () => {
    expect(homeFor("STUDENT")).toBe("/student");
  });

  it("sends staff to the console", () => {
    expect(homeFor("ADMIN")).toBe("/admin");
    expect(homeFor("FACULTY")).toBe("/admin");
  });
});
