"use client";
// Stat row for the public ADR check: every value is a field of /api/realworld's summary.
import type { RealWorldResponse } from "@/lib/types";
import { Docket } from "@/components/ui";
import { longDate } from "@/lib/format";

export default function RealWorldDocket({ summary, className }: { summary: RealWorldResponse["summary"]; className?: string }) {
  const items: [string, string][] = [
    ["Records", String(summary.records)],
    ["Repositories", String(summary.repos)],
    ["Checks", String(summary.checks)],
    ["Failing", String(summary.failing)],
    ["Unchecked", String(summary.unchecked)],
  ];
  if (summary.retired !== undefined) items.push(["Retired", String(summary.retired)]);
  items.push(["Checked on", longDate(summary.checked_on)]);
  return <Docket items={items} columns={items.length} className={className} />;
}
