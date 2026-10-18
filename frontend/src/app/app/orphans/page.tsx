import type { Metadata } from "next";
import OrphansView from "@/components/orphans/OrphansView";

export const metadata: Metadata = { title: "Owners" };

export default function Page() {
  return <OrphansView />;
}
