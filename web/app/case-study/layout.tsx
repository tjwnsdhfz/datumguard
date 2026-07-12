import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "CAD Assurance Case Study",
  description:
    "DatumGuard가 구조화 contract, serialized CAD 재입력, 독립 재측정과 fail-closed export gate로 설계 정확성 evidence를 만드는 방법",
  alternates: { canonical: "/case-study" },
  openGraph: {
    url: "/case-study",
    title: "DatumGuard CAD Assurance Case Study",
    description:
      "CAD command success is not accuracy evidence. Review the contract-to-artifact assurance pipeline, PASS/FAIL evidence, and explicit limits.",
  },
};

export default function CaseStudyLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
