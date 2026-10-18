"use client";
// Landing-page loaders for the middle sections. Each read is made once per page view and shared, so the
// how-it-works drawing and the path-verdict tile do not fetch D01 twice.
import { api } from "@/lib/api";

/** The spec's reference date: every landing example is read as of this day. */
export const REF_DATE = "2026-10-16";
export const TRAVEL_FROM = "2025-06-01";

const cache = new Map<string, Promise<unknown>>();

function once<T>(key: string, load: () => Promise<T>): Promise<T> {
  let p = cache.get(key) as Promise<T> | undefined;
  if (!p) {
    p = load();
    cache.set(key, p);
    p.catch(() => cache.delete(key)); // let a retry fetch again
  }
  return p;
}

export const loadD01 = () => once("D01@4", () => api.decision("D01", { as_of: REF_DATE, depth: 4 }));
export const loadD01Shallow = () => once("D01@1", () => api.decision("D01", { as_of: REF_DATE, depth: 1 }));
export const loadD07Then = () => once("D07@then", () => api.decision("D07", { as_of: TRAVEL_FROM, depth: 4 }));
export const loadD07Now = () => once("D07@now", () => api.decision("D07", { as_of: REF_DATE, depth: 4 }));
export const loadGate = () => once("gate", () => api.gate("D01", REF_DATE));
export const WHATIF_Q = "what if we no longer need SOC 2";
export const loadWhatIf = () => once("whatif", () => api.whatif({ q: WHATIF_Q, as_of: REF_DATE }));
export const loadOrphans = () => once("orphans", () => api.orphans({ as_of: REF_DATE }));

/** A promise that never settles: keeps `useApi` in its loading state until a section is armed. */
export const idle = <T,>() => new Promise<T>(() => {});
