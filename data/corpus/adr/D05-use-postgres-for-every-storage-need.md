# ADR D05: Use Postgres for every storage need

- Status: accepted
- Date: 2024-06-01
- Owner: Tomi Adeyemi (CTO)
- Systems: infra

## Context

We keep adding infrastructure. Every new datastore is another thing to back up, monitor, and explain to the auditor.

_No premise was recorded for this decision._

## Decision

No new datastore is introduced; queues, caches and documents all live in Postgres.

## Alternatives considered

- Redis for queues, S3 for documents (rejected)

## Consequences

Queues use SKIP LOCKED tables, caches are unlogged tables, documents are JSONB. Exceptions need a written ADR.
