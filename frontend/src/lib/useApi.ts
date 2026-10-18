"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/** Load data from the API. Re-runs when `deps` change; `reload()` refetches (e.g. after an approved write). */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const run = useCallback(() => {
    const n = ++seq.current;
    setLoading(true); setError(null);
    load().then(d => { if (n === seq.current) { setData(d); setLoading(false); } })
      .catch((e: Error) => { if (n === seq.current) { setError(e.message); setLoading(false); } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { data, error, loading, reload: run };
}
