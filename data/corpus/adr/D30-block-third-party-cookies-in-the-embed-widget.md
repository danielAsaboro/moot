# ADR D30: Block third-party cookies in the embed widget

- Status: accepted
- Date: 2025-11-05
- Owner: Sofia Rossi (Frontend lead)
- Systems: web-app

## Context

Chrome will remove third-party cookies in 2025. The embed widget relies on a third-party cookie to keep users signed in across customer sites, and that will simply stop working.

Stated premises:

- Chrome will remove third-party cookies in 2025. (assumption)

## Decision

The embeddable widget uses first-party storage only.

## Alternatives considered

- Storage Access API prompts (rejected: too many prompts per session)

## Consequences

The widget uses first-party storage with a short-lived token exchange. Expect more sign-in prompts on customer sites.
