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
  title: "DatumGuard | CAD Artifact Assurance",
  description:
    "건축·플랜트·기계 설계와 DXF·STEP·IFC 산출물을 독립 재측정하는 공학 CAD 정확성 포트폴리오",
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
