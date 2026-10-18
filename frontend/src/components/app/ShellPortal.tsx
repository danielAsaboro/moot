"use client";
// Renders its children into document.body. Sheets opened from inside the sticky ledger column or the blurred top
// bar would otherwise be trapped in their stacking context (sticky, backdrop-filter) and paint under the page.
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export default function ShellPortal({ children }: { children: ReactNode }) {
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => { setHost(document.body); }, []);
  return host ? createPortal(children, host) : null;
}
