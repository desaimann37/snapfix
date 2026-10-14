import type { Metadata } from "next";
import { ReportFlow } from "@/components/report-flow";

export const metadata: Metadata = { title: "Report a problem" };

export default function ReportPage() {
  return <ReportFlow />;
}
