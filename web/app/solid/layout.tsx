import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "STEP Solid Verification",
  description:
    "제한형 solid family의 STEP 생성, 격리 재입력, B-rep·치수 evidence를 보여주는 DatumGuard local/CI workspace",
  alternates: { canonical: "/solid" },
};

export default function SolidLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
