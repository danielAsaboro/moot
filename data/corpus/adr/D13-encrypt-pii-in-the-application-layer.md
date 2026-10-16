# ADR D13: Encrypt PII in the application layer

- Status: accepted
- Date: 2025-02-01
- Owner: Jonah Mbeki (Security engineer)
- Systems: billing

## Context

Enterprise customers ask for encryption with keys we control. RDS does not support customer-managed encryption keys in eu-central-1, so database-level encryption cannot satisfy that today.

Stated premises:

- RDS does not support customer-managed encryption keys in eu-central-1. (constraint)

## Decision

PII columns are encrypted by the application with our own keys before they reach the database.

## Alternatives considered

- Move to a region where RDS supports CMK (rejected: residency)
- Wait for AWS (rejected: no date)

## Consequences

The application encrypts PII columns with per-tenant keys from KMS before writing. Searching on encrypted columns is not possible; design around it.
