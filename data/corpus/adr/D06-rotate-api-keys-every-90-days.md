# ADR D06: Rotate API keys every 90 days

- Status: accepted
- Date: 2025-01-15
- Owner: Jonah Mbeki (Security engineer)
- Systems: auth

## Context

The SOC 2 auditor requires credential rotation at most every 90 days. Our keys currently never expire, which came up as a finding in the readiness assessment.

Stated premises:

- The SOC 2 auditor requires credential rotation at most every 90 days. (constraint)

## Decision

All service and customer API keys expire after 90 days and must be rotated.

## Alternatives considered

- Rotate on demand only (rejected: fails the control)

## Consequences

Keys carry an expiry; the auth service refuses expired keys; customers get a reminder at 14 and 3 days.
