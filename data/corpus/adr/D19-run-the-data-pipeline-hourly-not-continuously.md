# ADR D19: Run the data pipeline hourly, not continuously

- Status: accepted
- Date: 2025-08-01
- Owner: Lena Fischer (Data engineer)
- Systems: data-pipeline

## Context

Running the pipeline continuously looked attractive for freshness, but Warehouse query cost scales with how often the pipeline runs, and our warehouse bill tripled in the month we tried it.

Stated premises:

- Warehouse query cost scales with how often the pipeline runs. (fact)
  This holds because we are on BigQuery on-demand pricing.

## Decision

The pipeline batches events and runs once an hour.

## Alternatives considered

- Micro-batches every 5 minutes (rejected: same cost shape)
- Streaming into a cheaper store (deferred)

## Consequences

The pipeline runs hourly. Dashboards can be up to an hour behind. Revisit if the warehouse pricing model changes.
