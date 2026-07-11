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
  title: "DatumGuard | DXF 독립 검증 도구",
  description:
    "2D 플레이트를 폼으로 설계하고 생성된 DXF를 독립 재측정해 검증된 파일만 내려받는 공학 도면 도구",
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
