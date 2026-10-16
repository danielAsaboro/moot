# ADR D23: Use UUIDv4 for every primary key

- Status: accepted
- Date: 2024-06-15
- Owner: Priya Natarajan (Backend engineer)
- Systems: infra

## Context

Serial integer keys collide the moment data moves between databases. We plan to shard Postgres by tenant, and merging per-tenant tables with overlapping integer ids would be a migration from hell.

Stated premises:

- We plan to shard Postgres by tenant. (assumption)

## Decision

Tables use UUIDv4 primary keys instead of serial integers.

## Alternatives considered

- Snowflake-style ids (rejected: needs a coordinator service)
- ULIDs (deferred: no library we trusted at the time)

## Consequences

Every new table uses UUIDv4 primary keys. Index bloat is accepted. Revisit if the sharding plan changes.
