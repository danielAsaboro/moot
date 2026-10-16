# ADR D26: Retain logs for 30 days

- Status: accepted
- Date: 2024-08-01
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

Log storage costs about $0.50 per GB a month, and we were storing eighteen months of logs nobody read. The last three incidents used logs from the previous day.

Stated premises:

- Log storage costs about $0.50 per GB a month. (fact)

## Decision

Application logs are deleted after 30 days.

## Alternatives considered

- 90 days (rejected: cost)
- Cold storage after 30 days (deferred)

## Consequences

Logs are deleted after 30 days. Security events are exported separately with longer retention.
