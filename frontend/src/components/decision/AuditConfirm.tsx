"use client";
// Approval for the Summary view's writes, as a Sheet. Nothing reaches the graph until the reader presses the one accent
// button inside it; the rows above that button state exactly what will be written. After the write, the sheet shows
// the result and a Done button.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Sheet, cx } from "@/components/ui";
import s from "./Audit.module.css";

export type WriteState = { phase: "idle" | "busy" | "done" | "error"; message: string };

/** Runs one approved write and keeps its outcome for the sheet's status line. */
export function useWrite() {
  const [state, setState] = useState<WriteState>({ phase: "idle", message: "" });
  const run = useCallback(async (write: () => Promise<string>) => {
    setState({ phase: "busy", message: "" });
    try {
      setState({ phase: "done", message: await write() });
      return true;
    } catch (e) {
      setState({ phase: "error", message: e instanceof Error ? e.message : String(e) });
      return false;
    }
  }, []);
  const reset = useCallback(() => setState({ phase: "idle", message: "" }), []);
  return { state, run, reset };
}

/** Open/close state for one confirmation sheet plus its write. `close` is stable; after a successful write it
 *  calls `onChanged` (the panel reloads) only when the sheet closes, so the result stays readable until then. */
export function useConfirm(onChanged: () => void) {
  const [open, setOpen] = useState(false);
  const { state, run, reset } = useWrite();
  const latest = useRef({ state, onChanged });
  useEffect(() => { latest.current = { state, onChanged }; }, [state, onChanged]);
  const show = useCallback(() => { reset(); setOpen(true); }, [reset]);
  const close = useCallback(() => {
    const { state: st, onChanged: changed } = latest.current;
    if (st.phase === "busy") return;
    setOpen(false);
    if (st.phase === "done") changed();
    reset();
  }, [reset]);
  return { open, show, close, state, run };
}

export const NOTHING_WRITTEN = "Nothing is written until you approve.";

/** One-line outcome of a write, announced to screen readers. */
export function WriteStatus({ state }: { state: WriteState }) {
  if (state.phase === "idle") return <span role="status" className="sr-only" />;
  return (
    <p role="status" className={cx(s.status, state.phase === "error" && s.statusError, state.phase === "done" && s.statusDone)}>
      {state.phase === "busy" ? "Writing to the graph…" : state.phase === "error" ? `Not written. ${state.message}` : state.message}
    </p>
  );
}

/** The confirmation sheet: the statement of the write (children), one accent approve button, one footnote.
 *  `onClose` must be stable (useCallback): the Sheet re-focuses itself whenever it changes. */
export default function AuditConfirm({ open, title, onClose, children, approveLabel, onApprove, footnote, state, canApprove = true, action }: {
  open: boolean; title: string; onClose: () => void; children: ReactNode; approveLabel: string; onApprove: () => void;
  footnote: ReactNode; state: WriteState; canApprove?: boolean; action?: ReactNode;
}) {
  const busy = state.phase === "busy";
  const done = state.phase === "done";
  return (
    <Sheet open={open} title={title} onClose={onClose} cancelLabel={done ? "Close" : "Cancel"} action={action}>
      <div className={s.sheetBody}>{children}</div>
      <div className={s.sheetFoot}>
        <WriteStatus state={state} />
        {done ? (
          <button type="button" className={cx("btn", s.wide)} onClick={onClose}>Done</button>
        ) : (
          <>
            <button type="button" className={cx("btn accent", s.wide)} onClick={onApprove} disabled={busy || !canApprove}>
              {busy ? "Writing…" : approveLabel}
            </button>
            <p className={s.footnote}>{footnote}</p>
          </>
        )}
      </div>
    </Sheet>
  );
}
