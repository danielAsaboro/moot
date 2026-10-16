# ADR D25: Disable public sign-ups

- Status: accepted
- Date: 2025-10-01
- Owner: Tomi Adeyemi (CTO)
- Systems: web-app

## Context

Free-tier bots are abusing public sign-up: last month 80% of new accounts were bots creating workspaces to host spam. Captchas slowed them for a week.

Stated premises:

- Free-tier bots are abusing public sign-up. (fact)

## Decision

New accounts are created only through sales; the public sign-up form is off.

## Alternatives considered

- Email verification plus rate limits (rejected: tried, bypassed)
- Paid-only sign-up (rejected: kills trials)

## Consequences

The sign-up form is disabled; sales creates accounts. Marketing is told conversion from the site will drop.
