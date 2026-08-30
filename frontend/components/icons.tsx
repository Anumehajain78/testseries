import type { SVGProps } from "react";

export type IconName = "grid" | "file" | "plus" | "users" | "monitor" | "chart" | "shield" | "clock" | "calendar" | "arrow" | "check" | "alert" | "search" | "menu" | "close" | "flag" | "send" | "chevron" | "reset" | "building" | "user" | "book" | "wifi" | "logout";

const paths: Record<IconName, React.ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h5"/></>,
  plus: <path d="M12 5v14M5 12h14"/>, users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
  monitor: <><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></>, chart: <><path d="M3 3v18h18"/><path d="m7 15 4-4 4 2 5-7"/></>, shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>, calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>, arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>, check: <path d="m5 12 4 4L19 6"/>, alert: <><path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>, menu: <path d="M4 6h16M4 12h16M4 18h16"/>, close: <path d="m6 6 12 12M18 6 6 18"/>, flag: <><path d="M5 22V4"/><path d="M5 4h11l-1 5 1 5H5"/></>, send: <><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></>, chevron: <path d="m9 18 6-6-6-6"/>, reset: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></>,
  building: <><path d="M3 21h18M6 21V5l6-3 6 3v16M9 9h1M14 9h1M9 13h1M14 13h1M9 17h1M14 17h1"/></>, user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>, book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5Z"/><path d="M4 6.5v13"/></>, wifi: <><path d="M5 12.6a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="20" r=".5"/></>, logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/></>,
};

export function Icon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>{paths[name]}</svg>;
}
