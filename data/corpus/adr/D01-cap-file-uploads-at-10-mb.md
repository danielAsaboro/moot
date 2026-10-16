# ADR D01: Cap file uploads at 10 MB

- Status: accepted
- Date: 2025-02-10
- Owner: Ada Okafor (Platform lead)
- Systems: uploads-api

## Context

- All file uploads pass through the API gateway.
  This holds because the API gateway enforces a 10 MB request body limit.

## Decision

Reject any upload over 10 MB at the API with a clear error instead of letting it fail downstream.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
