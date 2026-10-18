"use client";
// "Read the decision record": a plain link that opens the source document in a sheet, loaded only when opened.
import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { Sheet } from "@/components/ui";
import s from "./Panel.module.css";

export default function PanelAdr({ id, source }: { id: string; source?: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  const show = () => {
    setOpen(true);
    if (text !== null || busy) return;
    setBusy(true); setError(null);
    api.document(`src:${id}`)
      .then(d => setText(d.text))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <button type="button" className="btn plain" onClick={show} aria-haspopup="dialog">Read the decision record</button>
      <Sheet open={open} onClose={close} title="Decision record" cancelLabel="Done">
        {source && <p className="t-footnote" style={{ margin: "0 4px" }}>From <span className="id">{source}</span></p>}
        {error ? <p className={s.err} role="alert">This record could not be loaded. {error}</p>
          : text === null ? <div className={s.adrSkel} aria-busy="true" aria-label="Loading the record"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" style={{ width: "60%" }} /></div>
          : <div className={s.doc} tabIndex={0} aria-label="Decision record text">{text}</div>}
      </Sheet>
    </>
  );
}
