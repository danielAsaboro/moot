"use client";
// Small browser hooks for the landing hero: media queries, reduced motion, visibility and theme colours.
import { useEffect, useState, type RefObject } from "react";

export function useMedia(query: string): boolean {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    const mq = matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return match;
}

export const useReducedMotion = () => useMedia("(prefers-reduced-motion: reduce)");

/** True while the element is at least partly on screen. */
export function useVisible(ref: RefObject<Element | null>): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") { setVisible(true); return; }
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.05 });
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return visible;
}

export interface Palette {
  surface: string; fill: string; separator: string; paper2: string; paper3: string;
  ink: string; ink2: string; ink3: string; accent: string; mootTint: string;
}

const VARS: Record<keyof Palette, string> = {
  surface: "--surface", fill: "--fill", separator: "--separator", paper2: "--paper-2", paper3: "--paper-3",
  ink: "--label", ink2: "--label-2", ink3: "--label-3", accent: "--accent", mootTint: "--moot-tint",
};

function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const out = {} as Palette;
  for (const k of Object.keys(VARS) as (keyof Palette)[]) out[k] = cs.getPropertyValue(VARS[k]).trim();
  return out;
}

/** The design tokens as colour strings, re-read when the theme toggle or the OS preference changes. */
export function usePalette(): Palette | null {
  const [pal, setPal] = useState<Palette | null>(null);
  useEffect(() => {
    const on = () => setPal(readPalette());
    on();
    const mo = new MutationObserver(on);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", on);
    return () => { mo.disconnect(); mq.removeEventListener("change", on); };
  }, []);
  return pal;
}
