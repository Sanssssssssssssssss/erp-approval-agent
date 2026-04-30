import type { Metadata } from "next";
import { IBM_Plex_Mono, VT323 } from "next/font/google";

import "./globals.css";

const monoBaseFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-body"
});

const monoFont = VT323({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-mono"
});

export const metadata: Metadata = {
  title: "ERP Approval Agent Workbench",
  description: "A local-first workbench for ERP approval recommendations, evidence retrieval, and audit traces."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className={`${monoBaseFont.variable} ${monoFont.variable}`}>
        {children}
      </body>
    </html>
  );
}
