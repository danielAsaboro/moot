"use client";
// /app/map/: the whole network as a transit map. Reasons are lines, decisions are stations on the line they rest on,
// dated evidence is an inspection or a break along it; scrub the months to watch lines close.
// Read-only: the data is GET /api/map, and "What if it broke?" asks GET /api/whatif.
import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAppState } from "@/lib/appState";
import EmptyState from "@/components/ui/EmptyState";
import { mountMetro } from "./metro";
import "./metro.css";

export default function MapView() {
  const { asOf, depth, link, selected } = useAppState();
  const router = useRouter();
  const sp = useSearchParams();
  const box = useRef<HTMLDivElement>(null);
  const res = useApi(() => api.map({ as_of: asOf, depth }), [asOf, depth]);

  // The renderer reads the link helper and the opening decision once per mount; keep the latest in a ref.
  const opts = useRef({ link, router, selected });
  opts.current = { link, router, selected };
  const first = useRef(sp.get("d"));

  useEffect(() => {
    const el = box.current, data = res.data;
    if (!el || !data) return;
    const initial = first.current; first.current = null;
    return mountMetro(el, data, {
      href: (path, extra) => opts.current.link(path, extra),
      navigate: href => opts.current.router.push(href),
      whatIf: (premise, as_of) => api.whatif({ premise, as_of, depth: data.depth }),
      initial,
    });
  }, [res.data]);

  if (res.error) return <EmptyState kind="error" title="The map could not load." detail={res.error} />;
  if (!res.data) return <EmptyState kind="loading" title="Drawing the network." detail="Reading every decision, reason and piece of dated evidence." />;
  return <div ref={box} className="mt" />;
}
