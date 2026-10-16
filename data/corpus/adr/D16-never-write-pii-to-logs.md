# ADR D16: Never write PII to logs

- Status: accepted
- Date: 2024-09-01
- Owner: Jonah Mbeki (Security engineer)
- Systems: infra

## Context

- GDPR applies to our EU users.

## Decision

Log lines are scrubbed of personal data before shipping.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
