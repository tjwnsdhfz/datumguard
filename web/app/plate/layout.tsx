import type { Metadata } from "next";
import type { ReactNode } from "react";

import { pageMetadata } from "../page-metadata";

export const metadata: Metadata = pageMetadata({
  title: "Engineering Plate DXF Verification",
  description:
    "Hole, slot, cutout, edge distance와 ligament를 구조화 contract와 serialized DXF 사이에서 검증하는 DatumGuard workspace",
  path: "/plate",
});

export default function PlateLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
