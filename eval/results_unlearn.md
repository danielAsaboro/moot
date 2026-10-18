# Un-learning: remembered gate answers, revoked when their evidence changes (study U1)

Every decision in Larkspur, the backtest and the four ingested repositories, asked about at every month start from its date to the snapshot, seeing only what was known then. *Stale* means the remembered answer differs from a fresh audit that month; a *stale clearance* is a remembered ALLOW served when a fresh audit would block. No model, no writes.

| policy | questions | answered from memory | stale answers served | stale clearances served |
|---|---|---|---|---|
| **Moot: serve while the rows' fingerprint is unchanged** | 12,792 | 12,514 (98%) | 0 | 0 |
| cache for 90 days | 12,792 | 8,456 (66%) | 62 | 0 |
| cache for a year | 12,792 | 11,613 (91%) | 285 | 0 |

| graph | decisions | Moot from memory | Moot stale | 90-day stale | 365-day stale |
|---|---|---|---|---|---|
| larkspur | 30 | 90% | 0 | 22 | 69 |
| backtest | 97 | 98% | 0 | 35 | 179 |
| gh_npryce_adr_tools | 9 | 99% | 0 | 0 | 0 |
| gh_thomvaill_log4brains | 11 | 98% | 0 | 2 | 29 |
| gh_alphagov_govuk_infrastructure | 24 | 97% | 0 | 1 | 7 |
| gh_alphagov_govuk_aws | 31 | 99% | 0 | 2 | 1 |

Moot's zero is by construction: the fingerprint covers every row the gate reads, so a change in any of them forces a re-audit. What the table measures is the price of that guarantee (how often memory still answers) and what a time-based cache gets wrong instead.
