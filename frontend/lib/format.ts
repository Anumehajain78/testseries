import type { ExamStatus } from "./types";

const dateTime = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const dateOnly = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const timeOnly = new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" });

export const formatDateTime = (value: string) => dateTime.format(new Date(value));
export const formatDate = (value: string) => dateOnly.format(new Date(value));
export const formatTime = (value: string) => timeOnly.format(new Date(value));
export const formatScore = (score: number, total: number) => `${score}/${total}`;
export const percentage = (score: number, total: number) => Math.round((score / total) * 100);
export const statusLabel = (status: ExamStatus) => ({ draft: "Draft", scheduled: "Scheduled", live: "Live now", completed: "Completed", cancelled: "Cancelled" })[status];
export const initials = (name: string) => name.split(" ").map((part) => part[0]).slice(0, 2).join("").toUpperCase();
export const formatDuration = (seconds: number) => {
  const safe = Math.max(0, seconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  return hours > 0 ? `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}` : `${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

// Human-readable "time since" a past timestamp, e.g. "just now", "45s ago", "3m ago".
// `nowMs` is injectable so a display tick can recompute against the current clock.
export const timeSince = (value: string | undefined, nowMs: number = Date.now()) => {
  if (!value) return "—";
  const seconds = Math.max(0, Math.round((nowMs - new Date(value).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m ago`;
};
