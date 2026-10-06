import type { Metadata } from "next";

import { SweepConsole } from "@/components/sweep/SweepConsole";

export const metadata: Metadata = { title: "Live sweep — SpineSight" };

export default function SweepPage() {
  return <SweepConsole />;
}
