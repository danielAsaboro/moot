// A small Markdown-to-HTML renderer for the blog posts in content/blog, run at build time.
// It covers what the posts use: headings, paragraphs, lists, block quotes, fenced code, bold, italic, inline code, links, images.

const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function inline(t: string): string {
  const codes: string[] = [];
  let s = esc(t).replace(/`([^`]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
  s = s
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?=[^*\w]|$)/g, "$1<em>$2</em>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
}

export function renderMarkdown(md: string): { title: string; html: string } {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let title = "";
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const body: string[] = [];
      for (i++; i < lines.length && !lines[i].startsWith("```"); i++) body.push(lines[i]);
      i++;
      out.push(`<pre${lang ? ` data-lang="${esc(lang)}"` : ""}><code>${esc(body.join("\n"))}</code></pre>`);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      if (h[1].length === 1 && !title) title = h[2];
      else out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
      i++;
      continue;
    }
    const img = /^!\[([^\]]*)\]\(([^)\s]+)\)\s*$/.exec(line);
    if (img) {
      out.push(`<figure><img src="${esc(img[2])}" alt="${esc(img[1])}" loading="lazy" /><figcaption>${inline(img[1])}</figcaption></figure>`);
      i++;
      continue;
    }
    if (/^\s*$/.test(line)) { i++; continue; }
    if (line.startsWith(">")) {
      const body: string[] = [];
      for (; i < lines.length && lines[i].startsWith(">"); i++) body.push(lines[i].replace(/^>\s?/, ""));
      out.push(`<blockquote><p>${inline(body.join(" "))}</p></blockquote>`);
      continue;
    }
    const list = /^(\s*)([-*]|\d+\.)\s+/.exec(line);
    if (list) {
      const ordered = /\d/.test(list[2]);
      const items: string[] = [];
      for (; i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i]); i++) items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""));
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((it) => `<li>${inline(it)}</li>`).join("")}</${tag}>`);
      continue;
    }
    const para: string[] = [];
    for (; i < lines.length && !/^\s*$/.test(lines[i]) && !/^(#{1,4}\s|```|>|\s*([-*]|\d+\.)\s)/.test(lines[i]); i++) para.push(lines[i]);
    out.push(`<p>${inline(para.join(" "))}</p>`);
  }
  return { title, html: out.join("\n") };
}
