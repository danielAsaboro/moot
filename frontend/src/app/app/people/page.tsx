import type { Metadata } from "next";
import PeopleView from "@/components/people/PeopleView";

export const metadata: Metadata = { title: "People" };

export default function Page() {
  return <PeopleView />;
}
