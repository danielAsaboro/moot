# ADR D20: Pin the mobile app to React Native 0.72

- Status: accepted
- Date: 2025-09-01
- Owner: Sofia Rossi (Frontend lead)
- Systems: mobile-app

## Context

React Native 0.74 defaults to the New Architecture. The payments SDK does not support the React Native New Architecture, and payments are the one part of the app we cannot ship without.

Stated premises:

- The payments SDK does not support the React Native New Architecture. (constraint)

## Decision

The mobile app stays on React Native 0.72 and the old architecture.

## Alternatives considered

- Fork the SDK (rejected: unmaintainable)
- Web checkout in a webview (rejected: conversion drop)

## Consequences

The app stays on 0.72 with the old architecture until the payments vendor ships support. Track their release notes.
