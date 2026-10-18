"""The README's charts, drawn as plain SVG from the result files, so they can never disagree with them.

  python3 eval/charts.py           write docs/charts/*.svg
  python3 eval/charts.py --check   exit 1 if a committed chart differs from what the result files draw (moot verify runs this)

Inputs: eval/results_baseline.json (study S3) and eval/results_reasons.json (stated reasons, before and after).
Each SVG carries its own light and dark colours (prefers-color-scheme), a <title> per mark, and no fonts to load.
"""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "charts"

STYLE = """<style>
.bg{fill:#fbfaf7}.t1{fill:#1d1d1b}.t2{fill:#5e5d58}.t3{fill:#8a8983}.grid{stroke:#e4e2dc}.axis{stroke:#bdbbb3}
.ink{fill:#1d1d1b}.muted{fill:#b9b7ae}.moot{fill:#b5372b}.holds{fill:#2f7d4f}.holdsu{fill:#9cc9ad}.retired{fill:#77756e}.undoc{fill:#dcd9d0}
.on-dark{fill:#fbfaf7}.on-light{fill:#1d1d1b}
@media (prefers-color-scheme: dark){.bg{fill:#1b1b1a}.t1{fill:#f0efec}.t2{fill:#c3c2b7}.t3{fill:#8f8e86}.grid{stroke:#34332f}.axis{stroke:#55544e}
.ink{fill:#f0efec}.muted{fill:#5f5e58}.moot{fill:#d9584a}.holds{fill:#3f9f66}.holdsu{fill:#2f5a41}.retired{fill:#8f8d85}.undoc{fill:#3d3c38}
.on-dark{fill:#1b1b1a}.on-light{fill:#f0efec}}
text{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
</style>"""


def svg(w: int, h: int, body: list[str], label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(label)}">\n'
            f"<title>{escape(label)}</title>\n{STYLE}\n<rect class=\"bg\" width=\"{w}\" height=\"{h}\" rx=\"14\"/>\n" + "\n".join(body) + "\n</svg>\n")


def bar(x: float, y: float, w: float, h: float, cls: str, tip: str, r: float = 4) -> str:
    """A bar with its data end rounded and its baseline end square."""
    w = max(w, 0.0)
    r = min(r, w / 2, h / 2)
    d = f"M{x:.1f},{y:.1f}h{w - r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r:.1f}a{r},{r} 0 0 1 -{r},{r}h-{w - r:.1f}z"
    return f'<path class="{cls}" d="{d}"><title>{escape(tip)}</title></path>'


def text(x, y, s, cls="t1", size=13, anchor="start", weight=400) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{escape(str(s))}</text>'


S3_ARMS = [  # (arm, label, group)
    ("moot", "Moot: graph verdict, depth 4", "moot"),
    ("moot_rows", "Moot rows, narrated by the model", "moot"),
    ("moot_depth1", "ablation: depth 1", "ablation"),
    ("rag_premises", "RAG over stated reasons (FalkorDB removed)", "rag"),
    ("rag_bm25", "RAG: BM25 top-5 + model", "rag"),
    ("moot_no_asof", "ablation: dates ignored (no as_of)", "ablation"),
    ("no_falkordb", "ablation: FalkorDB removed, rules kept", "ablation"),
    ("trust_adr", "trust the ADR", "rag"),
]


def s3_chart(B: dict) -> str:
    a, n = B["arms"], B["n"]
    W, left, right, top, row = 760, 300, 70, 74, 34
    H = top + row * len(S3_ARMS) + 58
    plot = W - left - right
    body = [text(24, 34, f"Study S3: verdicts right, of {n} questions", size=17, weight=600),
            text(24, 56, "Larkspur, 3 dates × 30 decisions. Same local model and prompt for every model arm.", "t2", 12.5)]
    for v in range(0, n + 1, 15):
        x = left + plot * v / n
        body.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 8}" y2="{top + row * len(S3_ARMS) - 6}" stroke-width="1"/>')
        body.append(text(x, top + row * len(S3_ARMS) + 10, v, "t3", 11, "middle"))
    for i, (arm, label, group) in enumerate(S3_ARMS):
        y = top + i * row
        v = a[arm]["verdict"]
        dead = len(a[arm]["dead_called_holds"])
        cls = "ink" if arm == "moot" else "muted"
        body.append(text(left - 12, y + 15, label, "t1" if group == "moot" else "t2", 13, "end", 600 if arm == "moot" else 400))
        body.append(bar(left, y, plot * v / n, 20, cls, f"{label}: {v}/{n} right, {dead} dead decisions called HOLDS"))
        body.append(text(left + plot * v / n + 8, y + 15, f"{v}", "t1", 13, "start", 600 if arm == "moot" else 400))
    body.append(text(24, H - 20, "Moot's 90/90 is a ceiling: Larkspur's labels share a spec with its graph. "
                                 "The ablations show what carries it: dates and the graph.", "t3", 11.5))
    return svg(W, H, body, f"Study S3 verdicts right of {n}: " + ", ".join(f"{l} {a[k]['verdict']}" for k, l, _ in S3_ARMS))


def s3_dead_chart(B: dict) -> str:
    a = B["arms"]
    dead_n = a["moot"]["dead_n"]
    arms = [x for x in S3_ARMS if x[0] in ("moot", "moot_depth1", "rag_premises", "no_falkordb", "rag_bm25", "trust_adr")]
    W, left, right, top, row = 760, 300, 70, 74, 34
    H = top + row * len(arms) + 58
    plot = W - left - right
    body = [text(24, 34, f"Dead decisions an assistant called HOLDS, of {dead_n}", size=17, weight=600),
            text(24, 56, "Lower is better. A dead decision is MOOT or DISPUTED on the date asked.", "t2", 12.5)]
    for v in range(0, dead_n + 1, 5):
        x = left + plot * v / dead_n
        body.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 8}" y2="{top + row * len(arms) - 6}" stroke-width="1"/>')
        body.append(text(x, top + row * len(arms) + 10, v, "t3", 11, "middle"))
    for i, (arm, label, group) in enumerate(arms):
        y = top + i * row
        v = len(a[arm]["dead_called_holds"])
        body.append(text(left - 12, y + 15, label, "t1" if group == "moot" else "t2", 13, "end", 600 if arm == "moot" else 400))
        body.append(bar(left, y, plot * v / dead_n, 20, "moot", f"{label}: {v} of {dead_n} dead decisions called HOLDS") if v else "")
        body.append(text(left + plot * v / dead_n + (8 if v else 2), y + 15, v, "t1", 13, "start", 600 if arm == "moot" else 400))
    body.append(text(24, H - 20, "Each one is an agent told it may keep enforcing a rule whose reason is gone.", "t3", 11.5))
    return svg(W, H, body, "Dead decisions called HOLDS: " + ", ".join(f"{l} {len(a[k]['dead_called_holds'])}" for k, l, _ in arms))


SEGMENTS = [("holds", "HOLDS, gate ALLOW (checked)"), ("holdsu", "HOLDS, gate REVALIDATE (reason stated, unevidenced)"),
            ("moot", "MOOT"), ("retired", "RETIRED"), ("undoc", "UNDOCUMENTED")]


def split(side: dict) -> dict:
    v = side["verdicts"]
    checked = side["holds_allow"]
    return dict(holds=checked, holdsu=v["HOLDS"] - checked, moot=v["MOOT"] + v.get("DISPUTED", 0), retired=v["RETIRED"], undoc=v["UNDOCUMENTED"])


def reasons_chart(R: dict) -> str:
    W, left, right, top = 760, 92, 24, 100
    plot = W - left - right
    rows = []
    for r in R["repos"]:
        rows.append((r["repo"], "before", split(r["before"]), r["decisions"]))
        rows.append(("", "after", split(r["after"]), r["decisions"]))
    H = top + len(R["repos"]) * (22 + 2 * 28 + 12) + 30
    body = [text(24, 34, "Verdicts per ingested repository, before and after reading stated reasons", size=17, weight=600),
            text(24, 56, f"Same day ({R['read_on']}), same tool checks, same verdict rules. Share of each repository's decisions.", "t2", 12.5)]
    lx = 24
    for cls, label in SEGMENTS:
        body.append(f'<rect class="{cls}" x="{lx}" y="68" width="12" height="12" rx="3"/>')
        short = label.split(" (")[0]
        body.append(text(lx + 17, 78.5, short, "t2", 11.5))
        lx += 17 + len(short) * 6.4 + 18
    y = top
    for repo, side, seg, n in rows:
        if repo:
            body.append(text(24, y + 13, f"{repo} · {n} decisions", "t1", 12.5, weight=600))
            y += 22
        body.append(text(left - 10, y + 14, side, "t2", 12, "end"))
        x = left
        for cls, label in SEGMENTS:
            k = seg[cls]
            if not k:
                continue
            w = plot * k / n
            body.append(f'<rect class="{cls}" x="{x:.1f}" y="{y}" width="{max(w - 2, 0.5):.1f}" height="20" rx="3"><title>{escape(repo or "")} {side}: {k} {escape(label)}</title></rect>')
            if w > 22:
                tc = "on-dark" if cls in ("holds", "moot", "retired") else "on-light"
                body.append(text(x + w / 2 - 1, y + 14.5, k, tc, 11.5, "middle", 600))
            x += w
        y += 28 if side == "before" else 40
    T = R["total"]
    body.append(text(24, H - 18, f"All four: UNDOCUMENTED {T['before']['verdicts']['UNDOCUMENTED']} → {T['after']['verdicts']['UNDOCUMENTED']} of {T['decisions']}. "
                                 f"Of {T['after']['verdicts']['HOLDS']} HOLDS after, {T['holds_checked']} are checked (ALLOW); the rest say why, unverified.", "t3", 11.5))
    return svg(W, H, body, "Verdicts before and after stated-reason extraction for " + ", ".join(r["repo"] for r in R["repos"]))


def charts() -> dict[str, str]:
    out = {}
    B = json.loads((ROOT / "eval" / "results_baseline.json").read_text())
    out["s3_verdicts.svg"] = s3_chart(B)
    out["s3_dead_called_holds.svg"] = s3_dead_chart(B)
    rp = ROOT / "eval" / "results_reasons.json"
    if rp.exists():
        out["reasons_before_after.svg"] = reasons_chart(json.loads(rp.read_text()))
    return out


def main() -> int:
    check = "--check" in sys.argv
    bad = []
    OUT.mkdir(parents=True, exist_ok=True)
    for name, s in charts().items():
        f = OUT / name
        if check:
            if not f.exists() or f.read_text() != s:
                bad.append(name)
        else:
            f.write_text(s)
            print("wrote", f.relative_to(ROOT))
    for b in bad:
        print("stale chart:", b, "(run python3 eval/charts.py)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
