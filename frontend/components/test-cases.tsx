"use client";

import { useId } from "react";
import type { BuilderTestCase } from "@/lib/test-cases";
import { Badge, Button, Field } from "./ui";

// ---------------------------------------------------------------------------
// The test-case editor
//
// One case, written the same way wherever it is written: while the paper is
// being composed, and while a wrong case is being corrected after the exam.
// Shared rather than copied because the visibility affordance is the part that
// decides what a candidate ever sees, and two versions of it would drift until
// one of them published an answer key.
// ---------------------------------------------------------------------------

/**
 * How much of the question the candidate can see, said as a count rather than
 * a colour alone: a paper with nothing hidden is one a candidate can see the
 * whole shape of, and that is a fact about the paper, not a styling choice.
 */
export function HiddenCaseCount({ tests }: { tests: BuilderTestCase[] }) {
  const hidden = tests.filter((test) => test.hidden).length;
  return <Badge tone={tests.length && hidden ? "success" : "warning"}>{hidden} of {tests.length} hidden</Badge>;
}

export function TestCaseFields({ label, test, onChange, onRemove }: {
  label: string;
  test: BuilderTestCase;
  onChange: (patch: Partial<BuilderTestCase>) => void;
  /** Absent when removing this case would leave the question unscorable. */
  onRemove?: () => void;
}) {
  const expectedId = useId();
  return <div className={`test-case ${test.hidden ? "is-hidden" : "is-visible"}`}>
    <div className="test-case-head"><strong>{label}</strong><Badge tone={test.hidden ? "neutral" : "info"}>{test.hidden ? "Hidden" : "Shown to candidates"}</Badge></div>
    <div className="test-case-io">
      <label className="field"><span>Input on stdin</span><textarea className="code-input" value={test.stdin} onChange={(e) => onChange({ stdin: e.target.value })} spellCheck={false} placeholder={"4\n1 2 3 4"}/></label>
      <div className="field">
        <label htmlFor={expectedId}>Expected output on stdout</label>
        <textarea id={expectedId} className="code-input" value={test.expectsNoOutput ? "" : test.expectedStdout} onChange={(e) => onChange({ expectedStdout: e.target.value })} disabled={test.expectsNoOutput} spellCheck={false} placeholder="10"/>
        {/* An empty expected output has to be chosen. Left blank it would
            award full marks to a program that prints nothing. */}
        <label className="expects-nothing"><input type="checkbox" checked={test.expectsNoOutput} onChange={(e) => onChange({ expectsNoOutput: e.target.checked, expectedStdout: e.target.checked ? "" : test.expectedStdout })}/><span>This case expects no output at all</span></label>
      </div>
    </div>
    <div className="test-case-foot">
      <label className="toggle-option"><input type="checkbox" checked={test.hidden} onChange={(e) => onChange({ hidden: e.target.checked })}/><span><strong>Hide from candidates</strong><small>{test.hidden ? "Neither this input nor its output reaches the paper." : "This input is printed on the paper as a sample."}</small></span></label>
      <Field label="Weight" type="number" min={1} value={test.weight} onChange={(e) => onChange({ weight: Number(e.target.value) })} hint="Share of the marks"/>
      {onRemove && <Button type="button" tone="ghost" onClick={onRemove}>Remove test</Button>}
    </div>
  </div>;
}
