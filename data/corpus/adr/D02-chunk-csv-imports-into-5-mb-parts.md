# ADR D02: Chunk CSV imports into 5 MB parts

- Status: accepted
- Date: 2025-03-01
- Owner: Priya Natarajan (Backend engineer)
- Systems: data-pipeline

## Context

Customer CSV imports regularly run to 40 or 50 MB. The API gateway enforces a 10 MB request body limit, so a single request cannot carry them. We do not want to run a separate ingestion endpoint outside the gateway.

Stated premises:

- The API gateway enforces a 10 MB request body limit. (constraint)

## Decision

Split customer CSV imports client-side into 5 MB parts and reassemble them in the pipeline.

## Alternatives considered

- SFTP drop (rejected: customers hate it and support hates it more)
- Compress before upload (rejected: still over the limit for the large accounts)

## Consequences

The import client splits files into 5 MB parts with a manifest; the pipeline reassembles and validates row counts. Partial imports are retried per part.
