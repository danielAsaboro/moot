"use client";
// App-wide view state for /app: the as-of date, premise depth and the selected decision, kept in the URL query
// (?as_of=2026-03-01&depth=4&d=D01) so a view can be linked and survives reloads.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

interface AppState {
  asOf: string | null;            // null = today
  depth: number;                  // 1..4 in the UI (the API accepts up to 6; the gate always uses 6)
  selected: string | null;        // decision id
  setAsOf: (d: string | null) => void;
  setDepth: (n: number) => void;
  select: (id: string | null) => void;
  /** href for another /app route that keeps as_of and depth */
  link: (path: string, extra?: Record<string, string>) => string;
}

const Ctx = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const asOf = sp.get("as_of");
  const depth = Math.max(1, Math.min(6, Number(sp.get("depth") ?? 4) || 4));
  const selected = sp.get("d");

  const update = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) (v === null || v === "" ? next.delete(k) : next.set(k, v));
    const q = next.toString();
    router.replace(`${pathname}${q ? `?${q}` : ""}`, { scroll: false });
  }, [sp, router, pathname]);

  const value = useMemo<AppState>(() => ({
    asOf, depth, selected,
    setAsOf: d => update({ as_of: d }),
    setDepth: n => update({ depth: String(n) }),
    select: id => update({ d: id }),
    link: (path, extra = {}) => {
      const q = new URLSearchParams();
      if (asOf) q.set("as_of", asOf);
      if (depth !== 4) q.set("depth", String(depth));
      for (const [k, v] of Object.entries(extra)) q.set(k, v);
      const s = q.toString();
      return `${path}${s ? `?${s}` : ""}`;
    },
  }), [asOf, depth, selected, update]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAppState must be used inside <AppStateProvider> (the /app layout)");
  return v;
}
