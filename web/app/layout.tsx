import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "@fontsource/noto-sans-kr/400.css";
import "@fontsource/noto-sans-kr/500.css";
import "@fontsource/noto-sans-kr/600.css";
import "@fontsource/noto-sans-kr/700.css";
import "@fontsource/noto-sans-kr/800.css";
import "./globals.css";
import "./architecture.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://datumguard-tjwnsdhfz.vercel.app"),
  applicationName: "DatumGuard",
  title: {
    default: "DatumGuard | Independent CAD Assurance",
    template: "%s | DatumGuard",
  },
  description:
    "설계 요구값을 contract로 고정하고 저장된 DXF·STEP을 별도 reader로 다시 측정해 검증된 파일만 승인하는 공학 CAD assurance 도구",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "ko_KR",
    url: "/case-study",
    siteName: "DatumGuard",
    title: "DatumGuard | Independent CAD Assurance",
    description:
      "Contract → serialized artifact → independent remeasurement → verified-only export.",
  },
  twitter: {
    card: "summary_large_image",
    title: "DatumGuard | Independent CAD Assurance",
    description:
      "CAD 자동화 결과를 별도 reader가 다시 측정하고 실패 시 공식 export를 차단합니다.",
  },
  category: "engineering",
};

export const viewport: Viewport = {
  colorScheme: "dark light",
  themeColor: "#000000",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
