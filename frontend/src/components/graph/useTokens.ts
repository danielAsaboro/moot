"use client";
// Reads the design tokens at runtime so the drawing follows the theme (data-theme on <html> and the OS preference)
// and the ground it sits on. Tokens are read from the drawing's own element, so a night ground set in CSS
// (`ground="night"` or an ancestor with data-ground="night") reaches the 3D scene too. The scene never hard-codes a colour.
import { useEffect, useState, type RefObject } from "react";

export interface Tokens {
  ground: string;   // --blueprint: paper in light, deep ink-blue in dark or on a night ground
  line: string;     // --blueprint-line: ink in light, pale blue-grey on a dark ground
  ink3: string; accent: string; holds: string; disputed: string;
  dark: boolean;    // the ground is dark (from its luminance, not the theme)
}

// Set on the drawing's root in IsoGraph.module.css (from --blueprint, --accent, …; switched on a night ground).
const VARS = { ground: "--iso-ground", line: "--iso-line", ink3: "--iso-muted", accent: "--iso-accent", holds: "--iso-holds", disputed: "--iso-disputed" } as const;

let ctx: CanvasRenderingContext2D | null = null;
/** Any CSS colour (hex, rgb, color-mix(), color(srgb …)) to "#rrggbb", by painting one pixel. */
function toHex(css: string): string {
  ctx ??= Object.assign(document.createElement("canvas"), { width: 1, height: 1 }).getContext("2d", { willReadFrequently: true });
  if (!ctx) return "#808080";
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = "#808080";
  ctx.fillStyle = css;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return `#${[r, g, b].map(n => n.toString(16).padStart(2, "0")).join("")}`;
}

function read(el: HTMLElement): Tokens {
  // A probe inside the element resolves var() and color-mix() to a used colour.
  const probe = document.createElement("span");
  probe.style.cssText = "position:absolute;width:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none";
  el.appendChild(probe);
  const out = {} as Record<keyof typeof VARS, string>;
  for (const [k, v] of Object.entries(VARS) as [keyof typeof VARS, string][]) {
    probe.style.color = `var(${v})`;
    out[k] = toHex(getComputedStyle(probe).color);
  }
  probe.remove();
  const n = parseInt(out.ground.slice(1), 16);
  const lum = (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
  return { ...out, dark: lum < 0.45 };
}

/** Tokens as seen from `ref`'s element. `key` forces a re-read when something the CSS depends on changes. */
export function useTokens(ref: RefObject<HTMLElement | null>, key = ""): Tokens | null {
  const [tokens, setTokens] = useState<Tokens | null>(null);
  useEffect(() => {
    const update = () => {
      const el = ref.current;
      if (!el) return;
      setTokens(prev => {
        const next = read(el);
        return prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
    };
    update();
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class", "style"] });
    // A section that switches its ground (data-ground="night") anywhere above the drawing.
    mo.observe(document.body, { attributes: true, subtree: true, attributeFilter: ["data-ground"] });
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    return () => { mo.disconnect(); mq.removeEventListener("change", update); };
  }, [ref, key]);
  return tokens;
}
