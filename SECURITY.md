# Security Policy

## Reporting a vulnerability

Email **neeljshah22@gmail.com** with the subject `CourtVision security`. Please include the
affected path or URL, reproduction steps, and impact. Do not open a public issue for anything
that exposes a credential, a private path, or a way to place or alter an order.

You can expect an acknowledgement within 72 hours.

## Scope

- This repository and the static site at https://neeljshah.github.io/court-vision/.
- The site is a static export: it has no login, no server-side state, and collects no user data.

## How this repository is protected

- `data/`, `vault/`, and planning trees are never committed; a pre-push guard
  (`scripts/hooks/prepush_guard.py`) refuses any push that touches a private tree or adds a
  credential pattern, and refuses non-fast-forward updates.
- Secrets live in environment variables only (`.env.example` lists names, never values).
- The order-lifecycle code has no reachable live path by default: it is double-gated and
  tested against a mock exchange (`scripts/platformkit/execution/executor/`).
- Public JSON published to the site passes a scrub and receipt check in CI before deploy
  (`webapp/scripts/verify-public-json.mjs`).
