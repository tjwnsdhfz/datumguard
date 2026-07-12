import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Plant Piping DXF Verification",
  description:
    "배관 route, support spacing, inline component, equipment clearance를 저장된 DXF에서 독립 재측정하는 DatumGuard workspace",
  alternates: { canonical: "/piping" },
};

export default function PipingLayout({ children }: Readonly<{ children: ReactNode }>) {
  return children;
}
