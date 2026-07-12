import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Engineering Plate DXF Verification",
  description:
    "Hole, slot, cutout, edge distance와 ligament를 구조화 contract와 serialized DXF 사이에서 검증하는 DatumGuard workspace",
  alternates: { canonical: "/plate" },
};

export default function PlateLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
