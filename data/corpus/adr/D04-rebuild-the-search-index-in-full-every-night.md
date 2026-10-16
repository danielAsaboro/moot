# ADR D04: Rebuild the search index in full every night

- Status: accepted
- Date: 2024-11-20
- Owner: Lena Fischer (Data engineer)
- Systems: search

## Context

- Our Elasticsearch mapping cannot take incremental updates.

## Decision

A nightly job drops and rebuilds the whole search index rather than applying updates.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
