import type { Metadata } from "next";
import GateBoard from "@/components/gate/GateBoard";

export const metadata: Metadata = { title: "Agent gate" };

export default function Page() {
  return <GateBoard />;
}
