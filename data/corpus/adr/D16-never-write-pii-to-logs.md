# ADR D16: Never write PII to logs

- Status: accepted
- Date: 2024-09-01
- Owner: Jonah Mbeki (Security engineer)
- Systems: infra

## Context

GDPR applies to our EU users. A log line with an email address in it is personal data in a system with 30-day retention and broad read access.

Stated premises:

- GDPR applies to our EU users. (constraint)

## Decision

Log lines are scrubbed of personal data before shipping.

## Alternatives considered

- Restrict log access instead (rejected: does not address retention)

## Consequences

The logging library scrubs known PII fields; a CI check fails on new log calls that pass user objects.
