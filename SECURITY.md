# Security policy

## Scope

This repository contains prompts (skills, an agent) and offline analyzer scripts. The scripts read local files and make no network calls.

## Reporting

Report a vulnerability or an unsafe instruction (a skill that could lead an agent to leak secrets, run destructive commands without approval, or follow injected content) through GitHub's private vulnerability reporting for this repository, or open a minimal issue without exploit details and ask for a private channel.

## Design commitments

- Read-only by default; mutating actions require explicit approval.
- Secrets are never printed; log and file content is treated as data, not instructions.
- Scripts do not execute input, do not download anything, and do not write outside the paths you give them.
