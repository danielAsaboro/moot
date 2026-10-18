import type { Metadata } from "next";
import AskView from "@/components/ask/AskView";

export const metadata: Metadata = { title: "Ask" };

export default function Page() {
  return <AskView />;
}
