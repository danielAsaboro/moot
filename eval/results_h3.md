# H3: ranking decisions by risk (study H3)

Registered in [docs/studies.md](../docs/studies.md) before any repository was chosen. GitHub code search found 489 repositories with an ADR folder; 447 had been used by no earlier study and all 447 were mined (`moot/heldout/h3.py`). Of their decisions, **29** pick a tool in the catalogue and were in force on 2022-10-17, from 12 repositories; by 2025-10-17 **none** had been abandoned by the H1 rule (gold: `eval/h3/gold.json`, sha256 pinned in `eval/h3/GOLD.sha256`).

**Result: underpowered, no claim.** The registered power rule needs at least 10 abandoned decisions in the test split; there are 0 in the whole set, so no ranking can be scored (AUC is undefined without a positive) and no score was computed. Most repositories that have an ADR folder today started keeping one after 2022, so few of their decisions were in force on the study date, and the few that were held.
