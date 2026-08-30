import type { Metadata } from "next";
import { ExamProvider } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Northbridge Exam Control", template: "%s · Northbridge" },
  description: "Institutional examination operations and secure student assessment platform.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><ExamProvider>{children}</ExamProvider></body></html>;
}
