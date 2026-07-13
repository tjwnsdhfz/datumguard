import type { Metadata } from "next";

import { pageMetadata } from "../page-metadata";
import FrameWorkspace from "./frame-workspace";

export const metadata: Metadata = pageMetadata({
  title: "FrameGuard | Structural Frame Screening",
  description:
    "A solver-verified structural frame screening demo for utility pipe racks. Locate governing members, inspect displacement, and keep engineering approval with the responsible engineer.",
  path: "/frame",
});

export default function FramePage() {
  return <FrameWorkspace />;
}
