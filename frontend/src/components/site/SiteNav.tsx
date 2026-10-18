"use client";
// Landing nav: a sticky blurred bar with the wordmark, a few quiet section links, one ink capsule and the theme toggle.
// On phones the section links hide; the wordmark, capsule and toggle stay.
import Link from "next/link";
import { ThemeToggle, Wordmark } from "@/components/ui";
import s from "./site.module.css";

const LINKS: [string, string][] = [
  ["#how", "How it works"],
  ["#drawing", "The drawing"],
  ["#proof", "Proof"],
  ["#gate", "Agents"],
  ["#world", "Real world"],
];

export default function SiteNav() {
  return (
    <header className={s.nav}>
      <div className={`wrap ${s.inner}`}>
        <Link href="/" className={s.brand} aria-label="Moot home"><Wordmark size={22} /></Link>
        <nav className={s.links} aria-label="Sections">
          {LINKS.map(([href, label]) => <a key={href} href={href}>{label}</a>)}
        </nav>
        <div className={s.right}>
          <Link href="/app/" className={s.cta}>Open the ledger</Link>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
