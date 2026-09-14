"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { AnswerValue, CodingLanguage, Question } from "@/lib/types";
import { formatDuration } from "@/lib/format";
import { WARNING_THRESHOLD_SECONDS, computeTimerState, createExpiryGuard } from "@/lib/exam-timer";
import { Icon } from "./icons";
import { Button, Modal, Progress } from "./ui";

export { WARNING_THRESHOLD_SECONDS };

// A question counts as answered when its normalized answer carries a real response.
export function isAnswered(value: AnswerValue | undefined): boolean {
  if (!value) return false;
  if (value.kind === "single") return value.option >= 0;
  if (value.kind === "multiple") return value.options.length > 0;
  // Starter code the candidate never touched is not saved, so whatever is here
  // is something they wrote — whitespace aside.
  if (value.kind === "code") return value.source.trim().length > 0;
  return value.text.trim().length > 0;
}

export function useExamTimer(endsAt: string | undefined, onExpire: () => void) {
  const calculate = useCallback(() => computeTimerState(endsAt), [endsAt]);
  const [timer, setTimer] = useState(calculate);
  const guard = useRef(createExpiryGuard());
  useEffect(() => {
    guard.current.reset();
    const tick = () => {
      const next = calculate();
      setTimer(next);
      if (guard.current.shouldExpire(next.remaining, endsAt)) onExpire();
    };
    tick();
    const interval = window.setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [calculate, endsAt, onExpire]);
  return timer;
}

export function ExamTimer({ endsAt, onExpire }: { endsAt?: string; onExpire: () => void }) { const { remaining, warning, urgent } = useExamTimer(endsAt, onExpire); return <div className={`exam-timer ${warning ? "warning" : ""} ${urgent ? "urgent" : ""}`} role="timer" aria-live={warning ? "polite" : "off"}><Icon name="clock"/><div><small>Time remaining</small><strong>{formatDuration(remaining)}</strong></div>{warning && <span className="sr-only">Warning: less than ten minutes remaining.</span>}</div>; }

// The palette is a jump target only while free navigation is permitted. With
// `allowNavigation: false` the exam is sequential, so it degrades to a
// read-only progress map rather than a way around the disabled Previous button.
export function QuestionPalette({ questions, current, answers, flags, allowNavigation = true, onSelect }: { questions: Question[]; current: number; answers: Record<string, AnswerValue>; flags: string[]; allowNavigation?: boolean; onSelect: (index: number) => void }) { const answered = questions.filter((question) => isAnswered(answers[question.id])).length; return <aside className="question-palette" aria-label="Question navigator"><div className="palette-heading"><div><p>Questions</p><strong>{answered} of {questions.length} answered</strong></div><span>{Math.round((answered / questions.length) * 100)}%</span></div><Progress value={(answered / questions.length) * 100}/><div className="palette-grid">{questions.map((question, index) => { const done = isAnswered(answers[question.id]); const locked = !allowNavigation && index !== current; return <button key={question.id} type="button" disabled={locked} className={`${current === index ? "current" : ""} ${done ? "answered" : ""} ${flags.includes(question.id) ? "flagged" : ""}`} onClick={() => { if (!locked) onSelect(index); }} aria-label={`Question ${index + 1}${done ? ", answered" : ", not answered"}${flags.includes(question.id) ? ", flagged" : ""}${locked ? ", locked" : ""}`} aria-current={current === index ? "step" : undefined}>{index + 1}{flags.includes(question.id) && <Icon name="flag" size={10}/>}</button>; })}</div>{!allowNavigation && <p className="palette-note">Sequential examination — revisiting earlier questions is disabled.</p>}<div className="palette-legend"><span><i className="legend-current"/> Current</span><span><i className="legend-answered"/> Answered</span><span><i className="legend-flagged"/> Flagged</span></div></aside>; }

const TYPE_HINT: Record<Question["type"], string> = { mcq: "Select one answer", multiple: "Select all that apply", text: "Write your answer", coding: "Write your program" };

// Four spaces, because the only language on offer is Python and four spaces is
// what PEP 8 asks for. A literal tab character would also be legal Python, but
// mixing the two in one file is not, and a candidate pasting an indented
// snippet from the prompt would produce exactly that mixture.
const INDENT = "    ";

// Exhaustive by key, so adding a runner on the backend breaks this build rather
// than labelling a candidate's editor with a raw enum value.
const LANGUAGE_LABEL: Record<CodingLanguage, string> = { python: "Python 3" };

/**
 * The candidate's code editor.
 *
 * A plain textarea, deliberately. This runs on lab workstations over the
 * college LAN, and a syntax-highlighting editor is a megabyte of JavaScript per
 * machine that has to arrive before anybody can type — which, in a room of
 * forty candidates opening the paper at the same second, is the difference
 * between starting on time and not starting.
 *
 * The draft lives here rather than being read straight back from the saved
 * answer: the save path is a network round trip, and a controlled textarea that
 * waits for the server before showing a keystroke is unusable for typing code.
 * The component is keyed by question id upstream, so moving between questions
 * remounts it instead of leaving the previous file on screen.
 */
function CodeAnswer({ question, saved, onAnswer }: { question: Question; saved?: string; onAnswer: (value: AnswerValue) => void }) {
  // The server sends a candidate only the visible cases; this filters again
  // regardless. The cost is one predicate, and what it guards against is
  // printing a hidden test on the very paper it was hidden from.
  const samples = (question.tests ?? []).filter((test) => !test.hidden);
  const starter = question.starterCode ?? "";
  const [source, setSource] = useState(saved ?? starter);
  // Tab is captured below, which takes away a keyboard-only candidate's way out
  // of the field. Escape arms one pass-through Tab — the convention assistive
  // technology teaches, and the reason the hint under the editor says it aloud.
  const escapeArmed = useRef(false);

  const write = (next: string, caret: number, field: HTMLTextAreaElement) => {
    setSource(next);
    onAnswer({ kind: "code", source: next });
    // The textarea is controlled, so the caret jumps to the end of the file on
    // the next render unless it is put back by hand. Indenting line three of a
    // solution must not dump the cursor at the bottom of it.
    requestAnimationFrame(() => { field.selectionStart = field.selectionEnd = caret; });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const field = event.currentTarget;
    const { selectionStart: start, selectionEnd: end } = field;
    if (event.key === "Escape") { escapeArmed.current = true; return; }
    if (event.key === "Tab") {
      if (escapeArmed.current || event.ctrlKey || event.altKey || event.metaKey) { escapeArmed.current = false; return; }
      event.preventDefault();
      if (!event.shiftKey) { write(source.slice(0, start) + INDENT + source.slice(end), start + INDENT.length, field); return; }
      // Outdent takes back whatever indent is actually there, up to one level;
      // taking a fixed four would eat a character of code off a short indent.
      const removable = /( {1,4})$/.exec(source.slice(Math.max(0, start - INDENT.length), start))?.[1];
      if (removable) write(source.slice(0, start - removable.length) + source.slice(start), start - removable.length, field);
      return;
    }
    escapeArmed.current = false;
    // Shift+Enter is left alone as the escape hatch: it is how a candidate gets
    // back to column zero after a block without deleting their way there.
    if (event.key !== "Enter" || event.shiftKey) return;
    // Python is whitespace-significant. A newline that returned to column zero
    // would make every loop body a manual re-indent.
    event.preventDefault();
    const lineStart = source.lastIndexOf("\n", start - 1) + 1;
    const line = source.slice(lineStart, start);
    const insert = `\n${/^[ \t]*/.exec(line)?.[0] ?? ""}${line.trimEnd().endsWith(":") ? INDENT : ""}`;
    write(source.slice(0, start) + insert + source.slice(end), start + insert.length, field);
  };

  return <div className="code-answer">
    {samples.length > 0 && <div className="code-samples">
      <p className="code-samples-head"><Icon name="code" size={15}/> Sample input{samples.length === 1 ? "" : "s"}<span>Your program is also run against further inputs you cannot see.</span></p>
      <ol>{samples.map((sample, sampleIndex) => <li key={sample.position}><small>Input {sampleIndex + 1}</small><pre>{sample.stdin || "This case sends no input."}</pre></li>)}</ol>
    </div>}
    <label className="sr-only" htmlFor={`${question.id}-code`}>{TYPE_HINT.coding}</label>
    <textarea
      id={`${question.id}-code`}
      className="code-editor"
      value={source}
      onChange={(event) => { setSource(event.target.value); onAnswer({ kind: "code", source: event.target.value }); }}
      onKeyDown={onKeyDown}
      spellCheck={false}
      autoCapitalize="off"
      autoCorrect="off"
      autoComplete="off"
      wrap="off"
      rows={16}
      aria-describedby={`${question.id}-code-help`}
    />
    <small id={`${question.id}-code-help`}>
      {/* Named only when this build recognises the runner. Telling a candidate
          they are writing Python when the server said something else would
          have them writing in the wrong language for the whole paper. */}
      {question.language ? LANGUAGE_LABEL[question.language] : "Program"} · Tab indents, Shift+Tab outdents, Esc then Tab leaves the editor.
      {" "}
      {source === starter ? "This is the starter code — nothing is recorded until you change it." : "Your code saves automatically."}
    </small>
  </div>;
}

export function QuestionCard({ question, index, total, answer, flagged, allowNavigation = true, onAnswer, onFlag, onPrevious, onNext }: { question: Question; index: number; total: number; answer?: AnswerValue; flagged: boolean; allowNavigation?: boolean; onAnswer: (value: AnswerValue) => void; onFlag: () => void; onPrevious: () => void; onNext: () => void }) {
  const single = answer?.kind === "single" ? answer.option : undefined;
  const multiple = answer?.kind === "multiple" ? answer.options : [];
  const text = answer?.kind === "text" ? answer.text : "";
  const code = answer?.kind === "code" ? answer.source : undefined;
  const toggleMultiple = (optionIndex: number) => {
    const set = new Set(multiple);
    if (set.has(optionIndex)) set.delete(optionIndex); else set.add(optionIndex);
    onAnswer({ kind: "multiple", options: [...set].sort((a, b) => a - b) });
  };
  return <article className="question-card"><div className="question-meta"><span>Question {index + 1} of {total}</span><span>{question.marks} marks</span></div><h2>{question.prompt}</h2>
    {question.type === "coding"
      ? <CodeAnswer key={question.id} question={question} saved={code} onAnswer={onAnswer}/>
      : question.type === "text"
      ? <div className="text-answer"><label className="sr-only" htmlFor={`${question.id}-text`}>{TYPE_HINT.text}</label><textarea id={`${question.id}-text`} value={text} onChange={(event) => onAnswer({ kind: "text", text: event.target.value })} placeholder="Type your response here…" rows={9}/><small>{text.trim().length} characters · responses save automatically</small></div>
      : <fieldset><legend className="sr-only">{TYPE_HINT[question.type]}</legend>{question.type === "multiple" && <p className="field-hint">Select all that apply.</p>}{question.options.map((option, optionIndex) => { const checked = question.type === "multiple" ? multiple.includes(optionIndex) : single === optionIndex; return <label key={option} className={`${checked ? "selected" : ""} ${question.type === "multiple" ? "is-multiple" : ""}`}><input type={question.type === "multiple" ? "checkbox" : "radio"} name={question.id} checked={checked} onChange={() => question.type === "multiple" ? toggleMultiple(optionIndex) : onAnswer({ kind: "single", option: optionIndex })}/><span className="option-letter">{String.fromCharCode(65 + optionIndex)}</span><span>{option}</span>{checked && <Icon name="check"/>}</label>; })}</fieldset>}
    <div className="question-actions"><Button tone={flagged ? "secondary" : "ghost"} icon="flag" onClick={onFlag}>{flagged ? "Unflag question" : "Flag for review"}</Button><div><Button tone="secondary" onClick={onPrevious} disabled={index === 0 || !allowNavigation}>Previous</Button><Button onClick={onNext} disabled={index === total - 1}>Save & Next <Icon name="arrow" size={17}/></Button></div></div></article>;
}

export function SubmitDialog({ open, onClose, onConfirm, answered, total }: { open: boolean; onClose: () => void; onConfirm: () => void; answered: number; total: number }) { const unanswered = total - answered; return <Modal open={open} onClose={onClose} title="Submit your assessment?" description="This action is final. You will not be able to change your answers after submission." actions={<><Button tone="secondary" onClick={onClose}>Return to exam</Button><Button icon="send" onClick={onConfirm}>Submit assessment</Button></>}><div className="submit-summary"><div><strong>{answered}</strong><span>Answered</span></div><div className={unanswered ? "warn" : ""}><strong>{unanswered}</strong><span>Unanswered</span></div></div></Modal>; }

export interface ReadinessCheck { label: string; detail: string; ok: boolean; }

// Reusable exam building block: renders the pre-exam readiness checklist (Req 12.2, 19.2).
export function SystemCheck({ checks }: { checks: ReadinessCheck[] }) {
  const ready = checks.every((check) => check.ok);
  return <div className="system-check"><div className="system-check-head"><div><Icon name="shield" size={16}/><strong>System readiness</strong></div><span className={ready ? "ok" : "pending"}><i/>{ready ? "All checks passed" : "Action needed"}</span></div><ul>{checks.map((check) => <li key={check.label} className={check.ok ? "ok" : "pending"}><span className="check-mark"><Icon name={check.ok ? "check" : "alert"} size={14}/></span><span className="check-body"><strong>{check.label}</strong><small>{check.detail}</small></span></li>)}</ul></div>;
}
