# ADR D02: Chunk CSV imports into 5 MB parts

- Status: accepted
- Date: 2025-03-01
- Owner: Priya Natarajan (Backend engineer)
- Systems: data-pipeline

## Context

- The API gateway enforces a 10 MB request body limit.

## Decision

Split customer CSV imports client-side into 5 MB parts and reassemble them in the pipeline.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
