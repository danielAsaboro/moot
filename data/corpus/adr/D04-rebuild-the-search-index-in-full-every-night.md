# ADR D04: Rebuild the search index in full every night

- Status: accepted
- Date: 2024-11-20
- Owner: Lena Fischer (Data engineer)
- Systems: search

## Context

The search index drifts from the database within hours because partial updates fail on the nested fields. Our Elasticsearch mapping cannot take incremental updates; the mapping change that would allow them is a multi-week migration nobody can staff this quarter.

Stated premises:

- Our Elasticsearch mapping cannot take incremental updates. (constraint)

## Decision

A nightly job drops and rebuilds the whole search index rather than applying updates.

## Alternatives considered

- Fix the mapping now (deferred to Q1)
- Dual-write with a reconciliation job (rejected: more moving parts than the problem deserves)

## Consequences

A nightly job at 02:00 UTC drops and rebuilds the index. Search results can be up to a day stale. Revisit when the mapping migration lands.
