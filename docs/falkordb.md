# How Moot uses FalkorDB

**The rule Moot enforces, in one sentence:** a decision is only as alive as the dated evidence behind its premises, and the graph, not the model, decides.

## Enforcement in three layers
1. **Schema.** Reasons are nodes (`Premise`), not text. Evidence relations carry `at` dates; ownership carries validity windows. Nothing about validity lives in prose.
2. **Query.** Verdicts come from `ro_query` path queries (`BECAUSE_OF|DERIVED_FROM*1..k` then `SUPPORTS|CONTRADICTS` filtered by `r.at <= $as_of`). The model receives rows and returns prose; a validator rejects any cited id the rows did not contain.
3. **Write gate.** The only write is `write_finding`, called after a human approves in the UI or the MCP client. It supersedes the previous finding so Moot's memory is itself time-ordered.

## Flow
question → `db.idx.fulltext.queryNodes` on `Decision` → `audit_decision` (path query) → `premise_impact` (`algo.pageRank`) for expired premises → `findings` (memory) → narrate → validate → UI shows `nodes(path)`.

## Endpoints / tools
| tool | query | read-only |
|---|---|---|
| find_decision | full-text index | yes |
| audit_decision | variable-length path + dated evidence | yes |
| premise_impact | reverse closure + `algo.pageRank` | yes |
| trace_document | `algo.SPpaths` evidence → decisions | yes |
| decision_owner | OWNS validity window | yes |
| ledger | one-pass audit of every decision | yes |
| check_action | the audit at depth 6 + dated SUPERSEDES / RETIRES, then the pure gate rule → ALLOW / DENY / REVALIDATE with the path | yes |
| record_finding | CREATE Finding + SUPERSEDED_BY | **write, approval-gated** |

## Failure states
| situation | state |
|---|---|
| question matches no decision | `unknown_entity`, no guess |
| decision id not present | `not_in_graph` |
| model narration cites an id outside the rows | narration rejected, template used, rejection shown |
| no model key, `MOOT_LLM=off`, or today's spend cap reached | keyword rules pick the tool, template narration; verdicts unaffected |
| the model picks an id the graph's catalogue did not list | pick rejected, keyword rules answer instead |
| verdict is UNDOCUMENTED, RETIRED or NOT_YET | answered from the rows with no model call (`narration: structural`) |
| a real-world check could not be answered | the premise exists, marked `unchecked`, with no evidence; the gate says REVALIDATE instead of guessing |
| FalkorDB unreachable | `/api/health` 503; UI shows a toast; nothing is served from a cache |

## Docs vs live differences found
- `CALL db.indexes()` fails on a graph that does not exist yet ("Invalid graph operation on empty key"); create indexes with try/except on "already indexed" instead of listing first.
- Multi-word full-text queries are AND by default (RediSearch syntax); Moot ORs prefix terms (`cap* | upload*`) and reranks by distinct terms matched.
- `ORDER BY length(p)` after `RETURN` needs the length projected (`length(p) AS hops`).
- `algo.pageRank(null, null)` runs over the whole graph; the `(label, relationship)` form restricts both.
- Tested on FalkorDB 4.18 (falkordblite) and the `falkordb/falkordb:latest` image.

## Scope
Single tenant seeded (`larkspur`); `MOOT_TENANT` selects another named graph. No vector index: entity resolution is full-text, by design, so the baseline comparison is apples to apples.
