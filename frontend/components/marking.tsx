"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { marking, type MarkingItemDto } from "@/lib/api";
import { useExam } from "@/app/providers";
import { Icon } from "./icons";
import { Badge, Button, ButtonLink, Card, EmptyState, LoadingState, PageHeader } from "./ui";

// ---------------------------------------------------------------------------
// Marking written answers
//
// Everything else on this platform is scored the moment a paper is submitted.
// Written answers cannot be, so until this screen existed a candidate could
// write a perfect answer and score nothing, with no way to put it right.
//
// The queue is ordered unmarked-first, because the job is finishing the ones
// nobody has read — a marked answer is shown so it can be revisited, not so it
// can be worked through again.
// ---------------------------------------------------------------------------

type Item = MarkingItemDto;

const key = (item: Item) => `${item.sessionId}:${item.questionId}`;

export function MarkingScreen() {
  const params = useParams<{ id: string }>();
  const { state, hydrated } = useExam();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});

  // Loading is a subscription to something outside React, so the state lands
  // in a callback rather than in the effect body.
  const load = useCallback(
    () =>
      marking
        .list(params.id)
        .then((rows) => {
          setItems(rows);
          setError(null);
        })
        .catch(() => setError("Could not load the written answers for this assessment.")),
    [params.id],
  );

  useEffect(() => {
    let cancelled = false;
    marking
      .list(params.id)
      .then((rows) => { if (!cancelled) setItems(rows); })
      .catch(() => { if (!cancelled) setError("Could not load the written answers for this assessment."); });
    return () => { cancelled = true; };
  }, [params.id]);

  const exam = state.tests.find((test) => test.id === params.id);

  // Unmarked first, then by candidate, so a marker works down the list without
  // choosing what to look at next.
  const ordered = useMemo(() => {
    if (!items) return [];
    return [...items].sort((a, b) => {
      const unread = Number(a.awardedMarks !== null) - Number(b.awardedMarks !== null);
      return unread !== 0 ? unread : a.studentName.localeCompare(b.studentName);
    });
  }, [items]);

  const remaining = ordered.filter((item) => item.awardedMarks === null).length;

  const award = async (item: Item, raw: string) => {
    const marks = Number(raw);
    if (!Number.isFinite(marks) || marks < 0 || marks > item.marks) {
      setError(`Enter a mark between 0 and ${item.marks}.`);
      return;
    }
    setSaving(key(item));
    setError(null);
    try {
      await marking.award(params.id, item.sessionId, item.questionId, marks);
      // Reload rather than patching locally: awarding re-grades the paper, and
      // the totals on the results screen have to agree with what happened here.
      await load();
      setDraft((current) => ({ ...current, [key(item)]: "" }));
    } catch {
      setError("That mark was not saved. Check the value and try again.");
    } finally {
      setSaving(null);
    }
  };

  if (!hydrated || items === null) return <LoadingState/>;

  return <>
    <PageHeader
      eyebrow="Marking"
      title={exam ? exam.title : "Written answers"}
      description="Read each answer and give it a mark. Totals update as you go."
      actions={<>
        <Badge tone={remaining ? "warning" : "success"}>
          {remaining ? `${remaining} left to mark` : "All marked"}
        </Badge>
        {exam && <ButtonLink href={`/admin/tests/${exam.id}`} tone="secondary">Assessment</ButtonLink>}
        <ButtonLink href="/admin/results" tone="ghost">Results</ButtonLink>
      </>}
    />

    {error && <div className="marking-error" role="alert"><Icon name="alert" size={17}/> {error}</div>}

    {ordered.length === 0
      ? <EmptyState
          icon="check"
          title="Nothing to mark"
          description="This assessment has no written answers. Everything else is scored automatically when a candidate submits."
          action={<ButtonLink href="/admin/results">See results</ButtonLink>}
        />
      : <div className="marking-list">
          {ordered.map((item) => {
            const id = key(item);
            const marked = item.awardedMarks !== null;
            const value = draft[id] ?? (marked ? String(item.awardedMarks) : "");
            return (
              <Card key={id} className={`marking-card ${marked ? "is-marked" : ""}`}>
                <div className="marking-head">
                  <div>
                    <strong>{item.studentName}</strong>
                    <small>{item.registrationNo}</small>
                  </div>
                  <Badge tone={marked ? "success" : "warning"}>
                    {marked ? `${item.awardedMarks} of ${item.marks}` : `Awaiting marking · ${item.marks} marks`}
                  </Badge>
                </div>

                <p className="marking-prompt">{item.prompt}</p>

                {/* The candidate's own words, kept as written rather than
                    reflowed, so a marker reads exactly what was submitted. */}
                <blockquote className="marking-response">
                  {item.response.trim() || <em>No answer was written.</em>}
                </blockquote>

                <div className="marking-actions">
                  <label className="field marking-mark">
                    <span>Marks out of {item.marks}</span>
                    <input
                      type="number"
                      min={0}
                      max={item.marks}
                      step="0.5"
                      value={value}
                      onChange={(event) => setDraft((current) => ({ ...current, [id]: event.target.value }))}
                      aria-label={`Marks for ${item.studentName}, out of ${item.marks}`}
                    />
                  </label>
                  <Button
                    type="button"
                    icon="check"
                    disabled={saving === id || value === ""}
                    onClick={() => award(item, value)}
                  >
                    {saving === id ? "Saving…" : marked ? "Update mark" : "Give mark"}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>}
  </>;
}
