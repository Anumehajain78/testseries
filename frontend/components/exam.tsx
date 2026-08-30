"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AnswerValue, Question } from "@/lib/types";
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

const TYPE_HINT: Record<Question["type"], string> = { mcq: "Select one answer", multiple: "Select all that apply", text: "Write your answer" };

export function QuestionCard({ question, index, total, answer, flagged, allowNavigation = true, onAnswer, onFlag, onPrevious, onNext }: { question: Question; index: number; total: number; answer?: AnswerValue; flagged: boolean; allowNavigation?: boolean; onAnswer: (value: AnswerValue) => void; onFlag: () => void; onPrevious: () => void; onNext: () => void }) {
  const single = answer?.kind === "single" ? answer.option : undefined;
  const multiple = answer?.kind === "multiple" ? answer.options : [];
  const text = answer?.kind === "text" ? answer.text : "";
  const toggleMultiple = (optionIndex: number) => {
    const set = new Set(multiple);
    if (set.has(optionIndex)) set.delete(optionIndex); else set.add(optionIndex);
    onAnswer({ kind: "multiple", options: [...set].sort((a, b) => a - b) });
  };
  return <article className="question-card"><div className="question-meta"><span>Question {index + 1} of {total}</span><span>{question.marks} marks</span></div><h2>{question.prompt}</h2>
    {question.type === "text"
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
