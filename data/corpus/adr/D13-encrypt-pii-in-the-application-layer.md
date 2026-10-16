# ADR D13: Encrypt PII in the application layer

- Status: accepted
- Date: 2025-02-01
- Owner: Jonah Mbeki (Security engineer)
- Systems: billing

## Context

- RDS does not support customer-managed encryption keys in eu-central-1.

## Decision

PII columns are encrypted by the application with our own keys before they reach the database.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
