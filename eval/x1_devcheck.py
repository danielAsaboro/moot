"""X1 dev check (no model): for each answerable question of the three dev products, the tool call that should hold the answer,
and whether its output does. A recall check of the tool layer only; it says nothing about an agent.

  python eval/x1_devcheck.py [--product VizForce] [--show]

Reads the dev products' questions (allowed by docs/studies.md X1) and refuses any other product. The call per question is
picked by fixed patterns on the question text below, standing in for the agent's choice. Scoring:
  ids / links / companies   recall of the ground-truth items found in the output text; rank questions also report whether
                            the tool's top set equals the ground truth exactly, PR questions the precision of the links returned
  content                   share of the ground truth's content words present in the output (hit at >= 0.6)
Needs the dev graph: `moot ingest-herb --product ExplainabilityForce --product CollaborateForce --product VizForce`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moot import herb_tools as t  # noqa: E402
from moot.connectors import herb  # noqa: E402

DOC = r"(Market Research Report|Product Vision Document|Product Requirements Document|Technical Specifications Document|System Design Document)"


def topic_of(q: str, product: str) -> str:
    m = re.search(r"(?:PRs?|links) (?:for|related to|to the PRs for|to PRs for|to the PRs related to|to PRs related to)\s+(?:the\s+)?(?:developing |setting up |updating )?(?:the\s+)?(.+?)\s+(?:feature\s+)?(?:in|for)\s+(?:the\s+)?" + product, q)
    if not m:
        m = re.search(r"for (?:the\s+)?(.+?) (?:in|for) " + product, q)
    s = m.group(1) if m else q
    return re.sub(r"^(?:links to |the |approved PRs for |PRs for |PRs related to )+", "", s).replace(" feature", "")


def route(q: str, p: str) -> tuple[str, list[tuple[str, dict]]]:
    """(question type, tool calls) for one question."""
    if (m := re.search(r"changes suggested by (.+?) to improve the " + DOC, q)):
        return "doc_feedback", [("doc_discussion", dict(product=p, doc_type=m.group(2), role=m.group(1)))]
    if (m := re.search(r"authors and key reviewers of the " + DOC, q)):
        return "doc_people", [("doc_discussion", dict(product=p, doc_type=m.group(1)))]
    if re.search(r"unique features|weaknesses of", q):
        return "competitor_content", [("competitors", dict(product=p))]
    if re.search(r"insights on the strengths", q):
        return "competitor_insight_people", [("competitors", dict(product=p))]
    if re.search(r"shared demos", q):
        return "competitor_demo_people", [("competitors", dict(product=p))]
    if re.search(r"demo URLs", q):
        return "competitor_demo_urls", [("links_shared", dict(product=p, kind="competitor_demo"))]
    if "PR" in q:
        status = ("to_close" if re.search(r"closed", q) else "to_merge" if re.search(r"merged\?|be merged", q) else
                  "reverted_direction" if re.search(r"product direction", q) else "reverted_bugs" if re.search(r"introduced bugs", q) else None)
        if re.search(r"authored maximum number of PRs .*reopened", q):
            return "rank_people", [("rank", dict(product=p, metric="fix_pr_authors", status="reopened"))]
        return f"prs_{status}", [("list_prs", dict(product=p, topic=topic_of(q, p), status=status))]
    if re.search(r"didn.t need fixes", q):
        return "rank_company", [("rank", dict(product=p, metric="issues_by_company", status="ever_dismissed"))]
    if re.search(r"company that has the maximum number of (unresolved|active) bugs", q):
        return "rank_company", [("rank", dict(product=p, metric="issues_by_company", status="unresolved"))]
    if re.search(r"company that has the maximum number of reopened", q):
        return "rank_company", [("rank", dict(product=p, metric="issues_by_company", status="reopened"))]
    if re.search(r"company that has the maximum number of resolved", q):
        return "rank_company", [("rank", dict(product=p, metric="issues_by_company", status="resolved"))]
    if re.search(r"dismissed maximum bugs .*reopened", q):
        return "rank_people", [("rank", dict(product=p, metric="issues_dismissed_by", status="reopened"))]
    if re.search(r"(assigned to|working on) the highest number of (active|unresolved)", q):
        return "rank_people", [("rank", dict(product=p, metric="issues_by_assignee", status="unresolved"))]
    if re.search(r"resolved the maximum number", q):
        return "rank_people", [("rank", dict(product=p, metric="issues_resolved_by", status="resolved"))]
    if (m := re.search(r"unresolved issues reported by (\w+)", q)):
        return "issues_content", [("list_issues", dict(product=p, company=m.group(1), status="unresolved"))]
    if (m := re.search(r"affected by issues in the (.+?) (?:in|of) " + p, q, re.I)):
        return "component_companies", [("list_issues", dict(product=p, component=m.group(1)))]
    if (m := re.search(r"resolved issues with the (.+?) (?:in|of) " + p, q, re.I)):
        return "component_resolvers", [("list_issues", dict(product=p, component=m.group(1), status="resolved"))]
    return "unrouted", []


STOP = set("the a an of in on for to and with is are be by as that this it its from at or into more include add".split())


def content_words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 2}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", action="append")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    products = a.product or list(herb.DEV)
    for p in products:
        if p not in herb.DEV:
            raise SystemExit(f"{p} is not a dev product; this script reads dev questions only")
    per = defaultdict(list)
    from moot.graph import graph
    blob = json.dumps(graph(herb.GRAPH).ro_query("MATCH (n) RETURN properties(n)").result_set, default=str)
    for p in products:
        raw = json.loads((herb.RAW / "products" / f"{p}.json").read_text())
        texts = [q["question"] if isinstance(q, dict) else q for k in ("answerable_questions", "unanswerable_questions") for q in raw[k]]
        leaked = [x for x in texts if json.dumps(x)[1:-1] in blob]
        print(f"{p}: {len(leaked)} of {len(texts)} question texts found in graph {herb.GRAPH}")
        qs = raw["answerable_questions"]
        for q in qs:
            kind, calls = route(q["question"], p)
            outs = [t.call(n, args) for n, args in calls]
            if kind.startswith("competitor_content"):  # the agent reads the discussions it was pointed to
                for c in json.loads(outs[0])["competitors"]:
                    for d in c["discussions"]:
                        outs.append(t.call("get_artifact", dict(id=d["first"], product=p)))
            text = " ".join(outs)
            gt = q["ground_truth"]
            exact = None
            if isinstance(gt, list):
                found = [x for x in gt if x in text]
                score = len(found) / len(gt) if gt else 0
                if kind.startswith("rank"):
                    exact = sorted(json.loads(outs[0]).get("top", [])) == sorted(gt)
                miss = [x for x in gt if x not in text]
                if kind.startswith("prs"):  # precision of the links the call returned
                    got = set(re.findall(r"https://github\.com/salesforce/[\w.-]+/pull/\d+", outs[0]))
                    exact = round(len(got & set(gt)) / len(got), 2) if got else 0.0
            else:
                gw = content_words(gt)
                score = len(gw & content_words(text)) / (len(gw) or 1)
                miss = sorted(gw - content_words(text))[:12]
            per[kind].append((score, exact))
            if a.show or score < 1:
                print(f"{p:<20} {kind:<26} {score:.2f}{'' if exact is None else ' x=' + str(exact):<11} {q['question'][:90]}")
                if score < 1:
                    print(f"{'':<20} calls={calls}\n{'':<20} missing={miss}")
    print("\nper question type (tool-layer recall on dev; content = word overlap, hit >= 0.6)")
    tot = []
    for k, v in sorted(per.items()):
        rec = sum(s for s, _ in v) / len(v)
        hits = sum(s >= (0.6 if k.endswith("content") or k == "doc_feedback" else 1.0) for s, _ in v)
        ex = [e for _, e in v if e is not None]
        tot += v
        extra = (f" precision={sum(ex) / len(ex):.2f}" if k.startswith("prs") else f" exact_top={sum(ex)}/{len(ex)}") if ex else ""
        print(f"  {k:<28} n={len(v):<3} recall={rec:.2f} full={hits}/{len(v)}" + extra)
    print(f"  {'all':<28} n={len(tot):<3} recall={sum(s for s, _ in tot) / len(tot):.2f}")


if __name__ == "__main__":
    main()
