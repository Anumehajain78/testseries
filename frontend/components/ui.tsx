"use client";

import { useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import Link from "next/link";
import { Icon, type IconName } from "./icons";
import { useExam } from "@/app/providers";
import type { BadgeTone, ConnectionStatus } from "@/lib/types";

export function Button({ children, tone = "primary", icon, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "danger" | "ghost"; icon?: IconName }) {
  return <button className={`btn btn-${tone} ${className}`} {...props}>{icon && <Icon name={icon} size={18}/>}<span>{children}</span></button>;
}
export function ButtonLink({ href, children, tone = "primary", icon, className = "" }: { href: string; children: ReactNode; tone?: "primary" | "secondary" | "ghost"; icon?: IconName; className?: string }) {
  return <Link href={href} className={`btn btn-${tone} ${className}`}>{icon && <Icon name={icon} size={18}/>}<span>{children}</span></Link>;
}
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) { return <span className={`badge badge-${tone}`}>{tone === "live" && <i/>}{children}</span>; }

export type StatusDotStatus = ConnectionStatus | "ready" | "occupied" | "maintenance";
const STATUS_DOT_TONE: Record<StatusDotStatus, "online" | "warning" | "offline"> = { online: "online", warning: "warning", offline: "offline", ready: "online", occupied: "warning", maintenance: "offline" };
const STATUS_DOT_LABEL: Record<StatusDotStatus, string> = { online: "Online", warning: "Warning", offline: "Offline", ready: "Ready", occupied: "Occupied", maintenance: "Maintenance" };
export function StatusDot({ status, label, showLabel = true }: { status: StatusDotStatus; label?: string; showLabel?: boolean }) {
  const tone = STATUS_DOT_TONE[status];
  const text = label ?? STATUS_DOT_LABEL[status];
  return <span className={`status-dot status-dot-${tone}`}><i aria-hidden="true"/>{showLabel ? <span>{text}</span> : <span className="sr-only">{text}</span>}</span>;
}
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section>; }
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) { return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="header-actions">{actions}</div>}</header>; }
export function StatCard({ label, value, detail, icon, tone = "navy" }: { label: string; value: string | number; detail: string; icon: IconName; tone?: "navy" | "teal" | "amber" | "blue" }) { return <Card className="stat-card"><div className={`stat-icon ${tone}`}><Icon name={icon}/></div><div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div></Card>; }

export function Field({ label, hint, error, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  const id = useId(); return <label className="field" htmlFor={id}><span>{label}</span><input id={id} aria-invalid={!!error} aria-describedby={hint || error ? `${id}-help` : undefined} {...props}/>{(hint || error) && <small id={`${id}-help`} className={error ? "field-error" : ""}>{error || hint}</small>}</label>;
}
export function Select({ label, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) { const id = useId(); return <label className="field" htmlFor={id}><span>{label}</span><select id={id} {...props}>{children}</select></label>; }
export function Progress({ value, label }: { value: number; label?: string }) { return <div className="progress-wrap">{label && <span>{label}</span>}<div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}><i style={{ width: `${Math.min(100, Math.max(0, value))}%` }}/></div></div>; }
export function TableShell({ caption, children }: { caption: string; children: ReactNode }) { return <div className="table-shell"><table><caption className="sr-only">{caption}</caption>{children}</table></div>; }
export function EmptyState({ icon = "file", title, description, action }: { icon?: IconName; title: string; description: string; action?: ReactNode }) { return <div className="empty"><span><Icon name={icon} size={28}/></span><h3>{title}</h3><p>{description}</p>{action}</div>; }

export function Modal({ open, onClose, title, description, children, actions }: { open: boolean; onClose: () => void; title: string; description?: string; children?: ReactNode; actions: ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null); const closeRef = useRef<HTMLButtonElement>(null); const previous = useRef<HTMLElement | null>(null);
  useEffect(() => { if (!open) return; previous.current = document.activeElement as HTMLElement; closeRef.current?.focus(); const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); if (event.key === "Tab" && dialogRef.current) { const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>("button, a, input, select, textarea, [tabindex]:not([tabindex='-1'])")]; if (!focusable.length) return; const first = focusable[0], last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }; document.addEventListener("keydown", key); return () => { document.removeEventListener("keydown", key); previous.current?.focus(); }; }, [open, onClose]);
  if (!open) return null;
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><div ref={dialogRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby={description ? "modal-description" : undefined}><button ref={closeRef} className="icon-button modal-close" onClick={onClose} aria-label="Close dialog"><Icon name="close"/></button><div className="modal-mark"><Icon name="alert"/></div><h2 id="modal-title">{title}</h2>{description && <p id="modal-description">{description}</p>}{children}<div className="modal-actions">{actions}</div></div></div>;
}

export function ToastViewport() { const { state, dismissToast } = useExam(); useEffect(() => { if (!state.toasts[0]) return; const timer = window.setTimeout(() => dismissToast(state.toasts[0].id), 4500); return () => clearTimeout(timer); }, [state.toasts, dismissToast]); return <div className="toast-viewport" aria-live="polite" aria-label="Notifications">{state.toasts.map((toast) => <div className={`toast toast-${toast.tone}`} key={toast.id}><Icon name={toast.tone === "success" ? "check" : "alert"}/><div><strong>{toast.title}</strong><p>{toast.message}</p></div><button className="icon-button" aria-label="Dismiss notification" onClick={() => dismissToast(toast.id)}><Icon name="close" size={16}/></button></div>)}</div>; }

export function LoadingState() { return <div className="loading-state"><span className="spinner"/><p>Synchronizing secure exam session…</p></div>; }
