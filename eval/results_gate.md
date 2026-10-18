# Gate eval: would an agent be allowed to act on a dead decision?

Larkspur, as of 2026-10-16: 30 decisions. An agent should act only on the 10 that HOLD; the other 20 (16 MOOT or DISPUTED, the rest UNDOCUMENTED or RETIRED) should be stopped.

| method | false allows (of 20) | 95% upper bound on false-allow rate | of which stale (of 16) | false blocks (of 10) | let through |
|---|---|---|---|---|---|
| Moot gate (depth 6) | **0** | 0.12 | **0** | **6** | – |
| same rule, depth 1 | 0 | 0.12 | 0 | 0 | – |
| BM25 top-5 + change cues | 4 | 0.38 | 4 | 8 | D11, D17, D25, D30 |
| trust the ADR | 20 | 1.00 | 16 | 0 | D01, D02, D03, D04, D05, D07, D08, D09, D11, D13, D17, D18, D19, D20, D21, D23, D25, D28, D29, D30 |

The upper bound is the one-sided 95% Wilson bound: 0 false allows in 20 still leaves room for a true rate up to 12%. Thirty decisions cannot show a gate is safe, only that it is not obviously unsafe.

**The Moot gate's 6 false blocks are all REVALIDATE, never DENY**: D06 (premise_unevidenced), D10 (premise_unevidenced), D16 (premise_unevidenced), D22 (premise_unevidenced), D26 (premise_unevidenced), D27 (premise_unevidenced). Each rests on a premise with no dated evidence either way. The spec calls these decisions HOLDS because nothing contradicts them; the gate refuses to let an agent act on that, because nothing ever checked them either. An owner's ruling (`POST /api/ruling`) is a dated edge that settles it. Until 2026-10-18 the gate printed "all premises hold" for them and scored 0 false blocks; that result is withdrawn ([docs/studies.md](../docs/studies.md)). The depth-1 row has no false blocks for the same reason it would miss a dead reason two hops down: it never looks at the unchecked premises below the stated one.

How the Moot gate decided:

- **ALLOW** (4): D12 (every premise has dated support), D14 (every premise has dated support), D15 (every premise has dated support), D24 (every premise has dated support)
- **DENY** (13): D01 (owner_left+premise_expired+premise_unevidenced), D02 (premise_expired), D03 (premise_expired), D07 (premise_expired), D08 (premise_expired), D09 (owner_left+premise_expired+premise_unevidenced), D13 (premise_expired), D18 (premise_expired), D19 (owner_left+premise_expired+premise_unevidenced), D20 (premise_expired), D25 (premise_expired), D28 (retired), D30 (premise_expired)
- **REVALIDATE** (13): D04 (owner_left+premise_disputed), D05 (undocumented), D06 (premise_unevidenced), D10 (premise_unevidenced), D11 (premise_disputed), D16 (premise_unevidenced), D17 (premise_disputed+premise_unevidenced), D21 (undocumented), D22 (premise_unevidenced), D23 (premise_disputed), D26 (premise_unevidenced), D27 (premise_unevidenced), D29 (undocumented)

Depth matters, but this corpus hides it: at depth 1, D01, D19 audit as HOLDS, because the reason that died is two hops below the one the ADR states. The depth-1 gate still stops them, but only on D01: owner_left, premise_unevidenced; D19: owner_left, premise_unevidenced, not on the dead reason. Those are reasons to ask, not a reason to stop: the depth-1 gate answers REVALIDATE where the full-depth gate answers DENY and names the contradicting evidence. The gate always audits at depth 6.

## Real public ADRs

25 records from 5 repositories, checked 2026-10-17. 23 of them still say *accepted*, so an agent that trusts the ADR would act on all of those.

| gate | records | why |
|---|---|---|
| DENY | 7 | bs-013: Retired on 2024-11-29 by bs-adr014 (Backstage ADR014: Proper use of HTTP fetching libraries (supersedes ADR013)).; ga-0006: "Puppet is actively maintained" was contradicted on 2026-10-17 by maintained:puppet.; gi-0007: Retired on 2025-07-21 by gi-0007-deprecated (GOV.UK ADR 0007 status changed to Deprecated).; gi-0013: "Prometheus Adapter is actively maintained" was contradicted on 2026-10-17 by maintained:prometheus-adapter.; gi-0020: "The current release of Crossplane has no known vulnerability" was contradicted on 2026-10-17 by no_known_vuln:crossplane.; l4b-lunr: "Lunr.js is actively maintained" was contradicted on 2026-10-17 by maintained:lunr.; moj-004: "The current release of Kubernetes has no known vulnerability" was contradicted on 2026-10-17 by no_known_vuln:kubernetes. |
| REVALIDATE | 7 | ga-0025: "The current release of Redis has no known vulnerability" could not be checked: no package in an OSV ecosystem.; gi-0002: "The current release of terraform-aws-eks module has no known vulnerability" could not be checked: no package in an OSV ecosystem.; gi-0004: "The current release of AWS Load Balancer Controller has no known vulnerability" could not be checked: the Go module's latest version (v1.1.9) does not match the project's latest release (v3.6.0).; gi-0008: "The current release of external-secrets has no known vulnerability" could not be checked: the Go module's latest version (v1.3.2) does not match the project's latest release (helm-chart-2.13.0).; gi-0010: "The current release of Dex has no known vulnerability" could not be checked: the Go module's latest version (v0.6.1) does not match the project's latest release (v2.46.0).; gi-0018: "The current release of Concourse CI has no known vulnerability" could not be checked: the Go module's latest version (v4.2.3+incompatible) does not match the project's latest release (v8.3.1).; moj-003: "The current release of Concourse CI has no known vulnerability" could not be checked: the Go module's latest version (v4.2.3+incompatible) does not match the project's latest release (v8.3.1). |
| ALLOW | 11 | every checked reason holds |

## Threats to validity, worst first

1. **Common-mode answer key.** The Larkspur answer key comes from the same spec as the graph, so the Moot row says the gate rule and the verdict rule agree, not that extraction is solved. The graph ablation ([results_ablation.md](results_ablation.md)) shows which edges the answers depend on.
2. **Small n.** 20 decisions to stop and 10 to allow; one decision moves a rate by 5–10 points. Read the bounds, not the zeros.
3. **Baselines without a model.** BM25 + cues and trust-the-ADR get no model, by design, so this file reproduces offline. The model-judged RAG baseline is study S3 (`eval/results_baseline.md`): with the same local model it calls 13 of 22 dead decisions HOLDS.
4. **Real ADRs have no answer key.** The second table reports what the gate did and on what evidence, not whether it was right.

REVALIDATE is not a verdict on the decision; it means the graph cannot vouch for it, which is exactly when an agent should stop.
