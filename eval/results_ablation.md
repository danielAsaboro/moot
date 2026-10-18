# Graph ablation: does the graph carry the gate's verdict?

Pre-registered as S1 in [docs/studies.md](../docs/studies.md) before the first run. Larkspur as of 2026-10-16: 10 decisions HOLD and may be acted on; 20 should be stopped, 16 of them MOOT or DISPUTED. Each cell is the mean over 20 random seeds (range in brackets) except at 0% and 100%, which are deterministic. *Legacy* is the gate before 2026-10-18, when a premise with no evidence counted as holding.

## Delete dated contradictions (14 edges)

| deleted | false allows, current (of 20) | stale allowed, current (of 16) | false allows, legacy | stale allowed, legacy | false blocks, current (of 10) |
|---|---|---|---|---|---|
| 0% | 0 | 0 | 0 | 0 | 6 |
| 25% | 0.55 (0–2) | 0.55 (0–2) | 3.35 (1–5) | 3.35 (1–5) | 6 |
| 50% | 0.95 (0–2) | 0.95 (0–2) | 6.35 (4–8) | 6.35 (4–8) | 6 |
| 75% | 1.45 (0–2) | 1.45 (0–2) | 8.6 (7–10) | 8.6 (7–10) | 6 |
| 100% | 2 | 2 | 12 | 12 | 6 |

## Delete reason edges: BECAUSE_OF and DERIVED_FROM (36 edges)

| deleted | false allows, current (of 20) | stale allowed, current (of 16) | false allows, legacy | stale allowed, legacy | false blocks, current (of 10) |
|---|---|---|---|---|---|
| 0% | 0 | 0 | 0 | 0 | 6 |
| 25% | 0 | 0 | 0 | 0 | 5.75 (3–8) |
| 50% | 0 | 0 | 0 | 0 | 7.2 (4–10) |
| 75% | 0 | 0 | 0 | 0 | 8.1 (6–9) |
| 100% | 0 | 0 | 0 | 0 | 10 |

## Add random contradictions (k = multiple of the 14 real ones)

| added | holds decisions denied, current (of 10) | false blocks, current (of 10) | holds denied, legacy | false blocks, legacy | false allows, current |
|---|---|---|---|---|---|
| 0 (0×) | 0 | 6 | 0 | 0 | 0 |
| 4 (0.25×) | 1.55 (0–5) | 6.55 (6–8) | 1.55 (0–5) | 2.05 (0–6) | 0 |
| 7 (0.5×) | 2.65 (0–6) | 7.15 (6–10) | 2.65 (0–6) | 3.6 (0–7) | 0 |
| 14 (1×) | 4 (0–7) | 7.4 (6–9) | 4 (0–7) | 5 (1–8) | 0 |
| 28 (2×) | 5.65 (2–8) | 8.7 (7–10) | 5.65 (2–8) | 7.7 (4–10) | 0 |

## Against the predictions in S1

At 0% the current gate lets through 0 of 20; the one-sided 95% upper bound on its false-allow rate is still 0.12.

1. **Legacy rule, delete contradictions: held.** False allows climb to 12 of 20 with every contradiction gone. Not all 16: the other stale decisions are still stopped because their owner left.
2. **Current rule, same deletion: held.** 2 of 20 get through. A premise whose only evidence was deleted becomes unevidenced and the gate asks to revalidate; only premises that also carry support (the disputed ones) read as holding.
3. **Reason-edge deletion: failed.** We predicted false allows would rise at middle fractions; the maximum over all seeds is 0 (legacy 0). Every stale Larkspur decision states exactly one premise, so cutting the chain to the dead premise either leaves the decision with no premise (UNDOCUMENTED, so REVALIDATE) or leaves one whose owner has left. What climbs instead is false blocks. This is a property of the corpus, not evidence that the rule is robust to missing reasons.
4. **Added contradictions: held.** Holds decisions denied climbs to 5.65 of 10 at 28 junk edges, and false allows stay at 0. The gate follows the edges it is given, junk included: it cannot tell a plausible wrong contradiction from a real one, which is why every DENY names the evidence id for a human to check.

## Threats to validity, worst first

1. The graph and the gold come from the same spec. The ablation shows which edges the gate's answers depend on; it does not show that those edges could be extracted from raw text.
2. Thirty decisions. A one-decision change is 3–10 points on these scales; the seed ranges show how much of each mean is the draw.
3. Random junk is easier to tell from real evidence than a plausible wrong edge an extractor would write. Real extraction errors would be more correlated with the decision's own vocabulary than these.
4. Deleting reason edges also removes the premises a decision is checked against, so part of what this arm measures is the gate's UNDOCUMENTED rule, not the evidence.
