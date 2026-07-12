import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Analytics } from "@vercel/analytics/next";

import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "@fontsource/noto-sans-kr/400.css";
import "@fontsource/noto-sans-kr/500.css";
import "@fontsource/noto-sans-kr/600.css";
import "@fontsource/noto-sans-kr/700.css";
import "@fontsource/noto-sans-kr/800.css";
import "./globals.css";
import "./architecture.css";

import { PRODUCTION_ORIGIN } from "../lib/site-config";
import SiteJsonLd from "./components/site-json-ld";

const HOME_TITLE = "DatumGuard | Independent CAD Assurance";
const HOME_DESCRIPTION =
  "AI가 요구값을 contract로 고정하고 저장된 DXF·STEP을 별도 reader로 다시 측정해 검증된 파일만 내보내는 공학 CAD assurance 도구";
const SOCIAL_IMAGE = {
  url: `${PRODUCTION_ORIGIN}/opengraph-image`,
  width: 1200,
  height: 630,
  alt: "DatumGuard independent CAD assurance pipeline",
};

export const metadata: Metadata = {
  metadataBase: new URL(PRODUCTION_ORIGIN),
  applicationName: "DatumGuard",
  title: {
    default: HOME_TITLE,
    template: "%s | DatumGuard",
  },
  description: HOME_DESCRIPTION,
  alternates: {
    canonical: `${PRODUCTION_ORIGIN}/`,
  },
  openGraph: {
    type: "website",
    locale: "ko_KR",
    url: `${PRODUCTION_ORIGIN}/`,
    siteName: "DatumGuard",
    title: HOME_TITLE,
    description: HOME_DESCRIPTION,
    images: [SOCIAL_IMAGE],
  },
  twitter: {
    card: "summary_large_image",
    title: HOME_TITLE,
    description:
      "CAD 자동화 결과를 별도 reader가 다시 측정하고 실패 시 공식 export를 차단합니다.",
    images: [SOCIAL_IMAGE.url],
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
      <body>
        <SiteJsonLd />
        {children}
        {process.env.VERCEL_ENV === "production" ? <Analytics /> : null}
      </body>
    </html>
  );
}
