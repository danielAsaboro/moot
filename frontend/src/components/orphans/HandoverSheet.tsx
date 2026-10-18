"use client";
// The one write on this page, behind an approval sheet: a new dated OWNS edge from the successor to the decision.
// It shows what will be written, writes only on "Approve handover", then shows the server's answer in place.
import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import type { OrphanDecision } from "@/lib/types";
import { longDate } from "@/lib/format";
import { Group, Row, Sheet } from "@/components/ui";
import s from "./orphans.module.css";

export interface HandoverResult { decision_id: string; to_name?: string; valid_from?: string; unchanged?: boolean }

interface Props {
  decision: OrphanDecision;
  from: { name: string };
  to: { id: string; name: string };
  date: string;                                   // ISO date the new OWNS edge starts
  href: string;                                   // the decision in the ledger
  onClose: () => void;                            // must be stable (the sheet re-focuses when it changes)
  onApprove: () => Promise<HandoverResult>;       // the write; throws with the server's message
}

export default function HandoverSheet({ decision, from, to, date, href, onClose, onApprove }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HandoverResult | null>(null);
  const busyRef = useRef(false);
  const close = useCallback(() => { if (!busyRef.current) onClose(); }, [onClose]);

  const approve = async () => {
    busyRef.current = true; setBusy(true); setError(null);
    try { setResult(await onApprove()); }
    catch (e) { setError((e as Error).message || "The server did not answer."); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const id = decision.id;
  const toName = result?.to_name ?? to.name;

  return (
    <Sheet open title={`Hand over ${id}`} onClose={close} cancelLabel={result ? "Done" : "Cancel"}>
      <div className={s.sheetBody}>
        <Group label={`Handover of ${id}`}>
          <Row title={decision.title} subtitle={<><span className="id">{id}</span>{decision.systems.length ? ` · ${decision.systems.join(", ")}` : ""}</>} />
          <Row title="From" trailing={<span className={s.kv}>{from.name}</span>} />
          <Row title="To" trailing={<span className={s.kv}>{to.name}</span>} />
          <Row title="Starting" trailing={<span className={s.kv}>{longDate(date)}</span>} />
        </Group>

        {result ? (
          <div className={s.done} role="status">
            <p>
              {result.unchanged
                ? <><span className="lead-in">Nothing written.</span> <span className="t-sub">{id} is already owned by {toName}.</span></>
                : <><span className="lead-in">Handed over.</span> <span className="t-sub">{toName} owns {id} from {longDate(result.valid_from ?? date)}. {from.name}&apos;s edge keeps its dates.</span></>}
            </p>
            <Link href={href} className="link">Open <span className="id">{id}</span> in the ledger ›</Link>
          </div>
        ) : (
          <>
            {error && <p className={s.sheetErr} role="alert"><b>Not written.</b> {error}</p>}
            <button type="button" className={`btn accent ${s.approve}`} onClick={approve} disabled={busy}>
              {busy ? "Writing…" : "Approve handover"}
            </button>
            <p className={s.sheetNote}>Writes a new dated OWNS edge. The old one keeps its dates.</p>
          </>
        )}
      </div>
    </Sheet>
  );
}
