import type { GateDecision, PremiseState, Verdict } from "./types";

export const VERDICT_ORDER: Verdict[] = ["MOOT", "DISPUTED", "UNDOCUMENTED", "HOLDS", "RETIRED"];

export const verdictLabel = (v: Verdict) => (v === "NOT_YET" ? "NOT YET DECIDED" : v === "NOT_IN_GRAPH" ? "NOT IN THE GRAPH" : v);

/** What each gate outcome asks of the reader, by its first reason. */
export function gateSummary(gate: GateDecision, firstReason?: string): string {
  if (gate === "ALLOW") return "an agent may act on this decision";
  if (gate === "DENY") return "an agent must not act on this decision";
  return ({
    undocumented: "record a reason before anyone acts on it",
    premise_disputed: "the owner has to rule before anyone acts on it",
    premise_unchecked: "a check could not be answered; verify it before anyone acts on it",
    premise_unevidenced: "no evidence either way; confirm it before anyone acts on it",
    owner_left: "nobody owns it; hand it over before anyone acts on it",
  } as Record<string, string>)[firstReason ?? ""] ?? "re-validate before anyone acts on it";
}

export const stateLabel = (s: PremiseState) => s;

/** "2026-03-02" -> "2 Mar 2026" */
export function longDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
