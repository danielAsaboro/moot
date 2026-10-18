"use client";
// "Ask it yourself": the exact read-only call an agent makes, and what each answer means. A quiet card.
import { Card, GateBadge, Group, Row } from "@/components/ui";
import type { GateDecision } from "@/lib/types";
import s from "./GateBoard.module.css";

const MEANING: [GateDecision, string][] = [
  ["DENY", "A reason is gone or contradicted, or the decision is retired."],
  ["REVALIDATE", "The graph cannot vouch for it. Check with the owner first."],
  ["ALLOW", "Every reason holds, with evidence."],
];

export default function AskPanel({ call }: { call: string | null }) {
  return (
    <Card as="section" className={s.ask}>
      <div className={s.askHead}>
        <h2 id="gate-ask-title" className="t-title3">Ask it yourself</h2>
        <p className="t-sub">
          <span className="lead-in">One read-only call per decision.</span> The same answer is an MCP tool for agents.
        </p>
      </div>
      <Group onSurface label="The call">
        <Row title={<code className={s.code}>{call ?? "GET /api/gate/{id}?as_of={date}"}</code>} subtitle="HTTP" />
        <Row title={<code className={s.code}>check_action</code>} subtitle="MCP tool" />
      </Group>
      <Group onSurface header={<span>What each answer means</span>} label="What each answer means">
        {MEANING.map(([g, text]) => (
          <Row key={g} leading={<span className={s.badgeCol}><GateBadge gate={g} /></span>} title={<span className={s.meaning}>{text}</span>} />
        ))}
      </Group>
    </Card>
  );
}
