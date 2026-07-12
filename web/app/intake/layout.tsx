import type { Metadata } from "next";
import type { ReactNode } from "react";

import { pageMetadata } from "../page-metadata";

export const metadata: Metadata = pageMetadata({
  title: "CAD Artifact Lab",
  description:
    "기존 DXF, STEP, IFC 파일을 변경하지 않고 구조와 revision evidence를 추출하는 DatumGuard informational audit workspace",
  path: "/intake",
});

export default function IntakeLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
