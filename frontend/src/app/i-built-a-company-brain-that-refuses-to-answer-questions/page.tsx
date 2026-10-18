// The Graph Hacks blog post, rendered from content/blog at build time into a static page.
import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import SiteFooter from "@/components/landing/SiteFooter";
import { ThemeToggle, Wordmark } from "@/components/ui";
import { renderMarkdown } from "@/lib/markdown";
import s from "./post.module.css";

const SLUG = "i-built-a-company-brain-that-refuses-to-answer-questions";
const BLOG = path.join(process.cwd(), "content", "blog");
const post = renderMarkdown(fs.readFileSync(path.join(BLOG, `${SLUG}.md`), "utf8"),
  (name) => fs.readFileSync(path.join(BLOG, "diagrams", `${name}.svg`), "utf8"));

export const metadata: Metadata = {
  title: post.title,
  description: "Why Moot audits the reasons behind decisions instead of answering questions, how FalkorDB decides the verdict, and the results I had to take back.",
  openGraph: { title: post.title, type: "article", url: `/${SLUG}/` },
};

export default function Post() {
  return (
    <>
      <header className={s.bar}>
        <div className={s.barInner}>
          <Link href="/" aria-label="Moot home"><Wordmark size={22} /></Link>
          <div className={s.barRight}>
            <Link href="/app/" className={s.cta}>Ask Moot</Link>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className={s.page}>
        <article className={s.prose}>
          <h1>{post.title}</h1>
          <div dangerouslySetInnerHTML={{ __html: post.html }} />
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
