# ADR D22: Review access grants every month

- Status: accepted
- Date: 2025-04-01
- Owner: Jonah Mbeki (Security engineer)
- Systems: auth

## Context

The SOC 2 auditor requires credential rotation at most every 90 days, and the same control expects access to be reviewed. We currently review access when someone leaves, which the auditor flagged as insufficient.

Stated premises:

- The SOC 2 auditor requires credential rotation at most every 90 days. (constraint)
  This holds because we need SOC 2 certification to sell to enterprise customers.

## Decision

A monthly review removes stale access to production systems.

## Alternatives considered

- Quarterly review (rejected: fails the control)

## Consequences

A monthly ticket lists every production grant; owners confirm or revoke within a week.
