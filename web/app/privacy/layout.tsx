import type { Metadata } from "next";
import type { ReactNode } from "react";

import { pageMetadata } from "../page-metadata";

export const metadata: Metadata = pageMetadata({
  title: "Privacy and Local Data",
  description:
    "DatumGuard의 stateless API, 브라우저 IndexedDB draft, 업로드 처리와 데이터 삭제 경계를 설명합니다.",
  path: "/privacy",
});

export default function PrivacyLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
