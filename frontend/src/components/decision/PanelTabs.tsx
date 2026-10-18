"use client";
// The four views of one audit as a segmented control: Summary, Graph, Steps, Queries (arrow keys move between them).
import { Segmented } from "@/components/ui";

export type PanelTab = "audit" | "graph" | "steps" | "cypher";
export const PANEL_TABS: [PanelTab, string][] = [["audit", "Summary"], ["graph", "Graph"], ["steps", "Steps"], ["cypher", "Cypher"]];
export const tabLabel = (t: PanelTab) => PANEL_TABS.find(([k]) => k === t)?.[1] ?? t;

export const tabId = (prefix: string, t: PanelTab) => `${prefix}-tab-${t}`;
export const paneId = (prefix: string, t: PanelTab) => `${prefix}-pane-${t}`;

export default function PanelTabs({ value, onChange, prefix }: { value: PanelTab; onChange: (t: PanelTab) => void; prefix?: string }) {
  void prefix;
  return <Segmented value={value} options={PANEL_TABS} onChange={onChange} label="Decision views" />;
}
