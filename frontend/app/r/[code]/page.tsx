import type { Metadata } from "next";
import { ReportFlow } from "@/components/report-flow";

export const metadata: Metadata = { title: "Report a problem" };

// QR stickers point here: /r/<location code>, e.g. /r/engr-101. The location is pre-filled.
export default function QrReportPage({ params }: { params: { code: string } }) {
  return <ReportFlow qrCode={decodeURIComponent(params.code)} />;
}
