# ADR D06: Rotate API keys every 90 days

- Status: accepted
- Date: 2025-01-15
- Owner: Jonah Mbeki (Security engineer)
- Systems: auth

## Context

- The SOC 2 auditor requires credential rotation at most every 90 days.

## Decision

All service and customer API keys expire after 90 days and must be rotated.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
