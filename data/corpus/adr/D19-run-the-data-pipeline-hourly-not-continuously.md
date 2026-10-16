# ADR D19: Run the data pipeline hourly, not continuously

- Status: accepted
- Date: 2025-08-01
- Owner: Lena Fischer (Data engineer)
- Systems: data-pipeline

## Context

- Warehouse query cost scales with how often the pipeline runs.
  This holds because we are on BigQuery on-demand pricing.

## Decision

The pipeline batches events and runs once an hour.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
