import type { Metadata } from "next";
import LedgerView from "@/components/app/LedgerView";

export const metadata: Metadata = { title: "Ledger" };

export default function Page() {
  return <LedgerView />;
}
