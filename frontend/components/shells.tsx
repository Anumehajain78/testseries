"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Icon, type IconName } from "./icons";
import { ToastViewport } from "./ui";
import { useExam } from "@/app/providers";
import { initials } from "@/lib/format";

const adminNav: Array<{ href: string; label: string; icon: IconName; exact?: boolean }> = [
  { href: "/admin", label: "Overview", icon: "grid", exact: true },
  { href: "/admin/tests", label: "Assessments", icon: "file" },
  { href: "/admin/students", label: "Students", icon: "users" },
  { href: "/admin/labs", label: "Labs & devices", icon: "monitor" },
  { href: "/admin/results", label: "Results", icon: "chart" },
  { href: "/admin/audit", label: "Audit log", icon: "shield" },
];

function Brand({ compact = false }: { compact?: boolean }) { return <Link className="brand" href="/"><span className="brand-mark"><Icon name="book" size={23}/></span>{!compact && <span><strong>Northbridge</strong><small>Exam Control</small></span>}</Link>; }

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(); const [menuOpen, setMenuOpen] = useState(false); const { resetDemo } = useExam();
  return <div className="admin-layout"><a className="skip-link" href="#main-content">Skip to main content</a><aside className={`sidebar ${menuOpen ? "open" : ""}`}><div className="sidebar-top"><Brand/><button className="icon-button mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><Icon name="close"/></button></div><nav aria-label="Administration"><p>Workspace</p>{adminNav.map((item) => { const active = item.exact ? pathname === item.href : pathname.startsWith(item.href); return <Link key={item.href} href={item.href} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => setMenuOpen(false)}><Icon name={item.icon}/><span>{item.label}</span>{item.label === "Assessments" && <small>4</small>}</Link>; })}</nav><div className="sidebar-help"><Icon name="shield"/><strong>Secure session</strong><p>Institution network verified</p></div><div className="sidebar-user"><span className="avatar">AR</span><div><strong>Anita Rao</strong><small>Exam Controller</small></div><button className="icon-button" onClick={resetDemo} title="Reset demo data" aria-label="Reset demo data"><Icon name="reset" size={18}/></button></div></aside>{menuOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)}/>}<div className="admin-main"><header className="topbar"><button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Icon name="menu"/></button><div className="topbar-context"><span className="live-dot"/> <span>Academic Year 2026–27</span><i/> <span>Odd Semester</span></div><div className="topbar-right"><span className="system-ok"><Icon name="wifi" size={16}/> All systems operational</span><button className="notification-button" aria-label="Notifications"><Icon name="alert" size={19}/><i/></button><span className="avatar small">AR</span></div></header><main id="main-content" className="content">{children}</main></div><ToastViewport/></div>;
}

export function StudentShell({ children }: { children: ReactNode }) {
  const pathname = usePathname(); const { state, currentStudentId } = useExam(); const student = state.students.find((item) => item.id === currentStudentId);
  const examMode = pathname.includes("/student/exam/");
  return <div className={`student-layout ${examMode ? "exam-mode" : ""}`}><a className="skip-link" href="#student-main">Skip to exam content</a><header className="student-header"><Brand/><div className="student-security"><span><Icon name="shield" size={16}/> Secure assessment environment</span>{student && <div className="student-id"><span className="avatar small">{initials(student.name)}</span><div><strong>{student.name}</strong><small>{student.registrationNo}</small></div></div>}</div></header><main id="student-main">{children}</main><footer className="student-footer"><span>© 2026 Northbridge Institute of Technology</span><span><Icon name="shield" size={14}/> Examination data is encrypted and monitored</span></footer><ToastViewport/></div>;
}
