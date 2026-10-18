import type { Metadata } from "next";
import RealWorldView from "@/components/shared/RealWorldView";

export const metadata: Metadata = { title: "Real-world proof" };

export default function Page() {
  return <RealWorldView />;
}
