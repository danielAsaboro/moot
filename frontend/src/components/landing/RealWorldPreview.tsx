"use client";
// Landing: the real public ADRs, checked against GitHub and OSV.dev. Five rows, the expired ones first, then a link to all.
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { SectionHead } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";
import RealWorldIndex from "@/components/shared/RealWorldIndex";
import s from "./RealWorldPreview.module.css";

const SHOWN = 5;
const REASONS = "Each tool choice rests on reasons nobody wrote down: still maintained, still open source, no known vulnerability.";

export default function RealWorldPreview() {
  const { data, error, loading, reload } = useApi(() => api.realworld(), []);
  const lead = data
    ? `${data.summary.records} records from ${data.summary.repos} GitHub repositories. ${REASONS}`
    : REASONS;
  return (
    <section id="world" className={s.section} aria-label="Real world">
      <div className="wrap">
        <SectionHead eyebrow="Real world" title="Checked against public decision records.">{lead}</SectionHead>
        <div className={s.body}>
          {loading && !data && (
            <div className={s.skel} aria-busy="true" aria-label="Loading the public records">
              {Array.from({ length: SHOWN }, (_, i) => <div key={i} className="skeleton" style={{ height: 44 }} />)}
            </div>
          )}
          {error && <EmptyState kind="error" title="The public records could not be loaded." detail={error}
            action={<button type="button" className="btn ghost small" onClick={reload}>Try again</button>} />}
          {data && (
            <RealWorldIndex data={data} compact limit={SHOWN}
              after={<Link href="/app/realworld/" className="link">See all {data.decisions.length} records <span aria-hidden="true">›</span></Link>} />
          )}
        </div>
      </div>
    </section>
  );
}
