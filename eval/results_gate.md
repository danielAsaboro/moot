# Gate eval: would an agent be allowed to act on a dead decision?

Larkspur, as of 2026-10-16: 30 decisions. An agent should act only on the 10 that HOLD; the other 20 (16 MOOT or DISPUTED, the rest UNDOCUMENTED or RETIRED) should be stopped.

| method | false allows (of 20) | of which stale (of 16) | false blocks (of 10) | let through |
|---|---|---|---|---|
| Moot gate (depth 6) | **0** | **0** | **0** | – |
| same rule, depth 1 | 0 | 0 | 0 | – |
| BM25 top-5 + change cues | 4 | 4 | 8 | D11, D17, D25, D30 |
| trust the ADR | 20 | 16 | 0 | D01, D02, D03, D04, D05, D07, D08, D09, D11, D13, D17, D18, D19, D20, D21, D23, D25, D28, D29, D30 |

How the Moot gate decided:

- **ALLOW** (10): D06 (all premises hold), D10 (all premises hold), D12 (all premises hold), D14 (all premises hold), D15 (all premises hold), D16 (all premises hold), D22 (all premises hold), D24 (all premises hold), D26 (all premises hold), D27 (all premises hold)
- **DENY** (13): D01 (owner_left+premise_expired), D02 (premise_expired), D03 (premise_expired), D07 (premise_expired), D08 (premise_expired), D09 (owner_left+premise_expired), D13 (premise_expired), D18 (premise_expired), D19 (owner_left+premise_expired), D20 (premise_expired), D25 (premise_expired), D28 (retired), D30 (premise_expired)
- **REVALIDATE** (7): D04 (owner_left+premise_disputed), D05 (undocumented), D11 (premise_disputed), D17 (premise_disputed), D21 (undocumented), D23 (premise_disputed), D29 (undocumented)

Depth matters, but this corpus hides it: at depth 1, D01, D19 audit as HOLDS, because the reason that died is two hops below the one the ADR states. The depth-1 gate still stops them, but only on D01: owner_left; D19: owner_left, not on the dead reason. Hand either decision to an owner who is still here and a depth-1 gate lets it through. The gate always audits at depth 6, where the contradicting evidence itself is the reason it denies.

## Real public ADRs

25 records from 5 repositories, checked 2026-10-17. 23 of them still say *accepted*, so an agent that trusts the ADR would act on all of those.

| gate | records | why |
|---|---|---|
| DENY | 7 | bs-013: Retired on 2024-11-29 by bs-adr014 (Backstage ADR014: Proper use of HTTP fetching libraries (supersedes ADR013)).; ga-0006: "Puppet is actively maintained" was contradicted on 2026-10-17 by maintained:puppet.; gi-0007: Retired on 2025-07-21 by gi-0007-deprecated (GOV.UK ADR 0007 status changed to Deprecated).; gi-0013: "Prometheus Adapter is actively maintained" was contradicted on 2026-10-17 by maintained:prometheus-adapter.; gi-0020: "The current release of Crossplane has no known vulnerability" was contradicted on 2026-10-17 by no_known_vuln:crossplane.; l4b-lunr: "Lunr.js is actively maintained" was contradicted on 2026-10-17 by maintained:lunr.; moj-004: "The current release of Kubernetes has no known vulnerability" was contradicted on 2026-10-17 by no_known_vuln:kubernetes. |
| REVALIDATE | 7 | ga-0025: "The current release of Redis has no known vulnerability" could not be checked: no package in an OSV ecosystem.; gi-0002: "The current release of terraform-aws-eks module has no known vulnerability" could not be checked: no package in an OSV ecosystem.; gi-0004: "The current release of AWS Load Balancer Controller has no known vulnerability" could not be checked: the Go module's latest version (v1.1.9) does not match the project's latest release (v3.6.0).; gi-0008: "The current release of external-secrets has no known vulnerability" could not be checked: the Go module's latest version (v1.3.2) does not match the project's latest release (helm-chart-2.13.0).; gi-0010: "The current release of Dex has no known vulnerability" could not be checked: the Go module's latest version (v0.6.1) does not match the project's latest release (v2.46.0).; gi-0018: "The current release of Concourse CI has no known vulnerability" could not be checked: the Go module's latest version (v4.2.3+incompatible) does not match the project's latest release (v8.3.1).; moj-003: "The current release of Concourse CI has no known vulnerability" could not be checked: the Go module's latest version (v4.2.3+incompatible) does not match the project's latest release (v8.3.1). |
| ALLOW | 11 | every checked reason holds |

Limits: the Larkspur answer key comes from the same spec as the graph, so the Moot row says the gate rule and the verdict rule agree, not that extraction is solved. The baselines get no model, by design, so this file reproduces offline. REVALIDATE is not a verdict on the decision; it means the graph cannot vouch for it, which is exactly when an agent should stop.
