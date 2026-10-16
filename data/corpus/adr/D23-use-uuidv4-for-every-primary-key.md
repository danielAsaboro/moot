# ADR D23: Use UUIDv4 for every primary key

- Status: accepted
- Date: 2024-06-15
- Owner: Priya Natarajan (Backend engineer)
- Systems: infra

## Context

- We plan to shard Postgres by tenant.

## Decision

Tables use UUIDv4 primary keys instead of serial integers.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
