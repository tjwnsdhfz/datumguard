import type { Metadata } from "next";
import type { ReactNode } from "react";

import { pageMetadata } from "../page-metadata";

export const metadata: Metadata = pageMetadata({
  title: "OpenBIM Evidence Guard",
  description:
    "IFC4 기준 모델과 후보 모델을 IDS 1.0 요구사항, 무결성, 변경 보호 규칙으로 검증하고 재현 가능한 증거를 내보내는 연구용 OpenBIM 작업공간",
  path: "/openbim",
});

export default function OpenBimLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
