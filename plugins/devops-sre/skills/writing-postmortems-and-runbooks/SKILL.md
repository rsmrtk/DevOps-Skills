---
name: writing-postmortems-and-runbooks
description: Writes blameless postmortems and actionable runbooks from real incident evidence, and states which metrics (MTTR, impact) can and cannot be computed. Use when the user asks for a postmortem, incident report, timeline, root cause analysis, or a runbook for an alert.
---

# Postmortems and runbooks

Evidence before narrative. Collect first, write second. Mark every claim `confirmed` (with source) or `inferred`.

## Collect

```
- [ ] Alert/detection time and source        - [ ] Deploys and config changes in the window
- [ ] First user impact time                  - [ ] Metrics: errors, latency, saturation
- [ ] Mitigation start and resolution time    - [ ] Relevant logs (quote exact lines)
```
Pull the deploy/change timeline for the hour before impact; most incidents correlate with a change. A correlation is not a cause: say "preceded", and test the hypothesis (rollback result, reproduction).

## Postmortem template (blameless)

```markdown
# <Service>: <one-line impact> — <date>
**Status:** draft | reviewed   **Severity:** SEV?   **Duration:** <start> – <end> (<N> min)

## Summary
Two or three sentences: what broke, who was affected, how it was fixed.

## Impact
Who/what was affected, for how long, how it was measured. Error budget burned: <X% or "not measured">.

## Timeline (UTC)
| Time | Event | Source |
|---|---|---|

## Root cause
Mechanism, not a person. Separate **trigger** (what happened) from **conditions** (why it was possible).

## What went well / what went badly / where we got lucky

## Action items
| Action | Type (prevent/detect/mitigate) | Owner | Due |
|---|---|---|---|
```
Rules: no names as causes ("the deploy" not "Alex's deploy"); every action has an owner and a date;
prefer actions that remove a class of failure over "be more careful".

## Metrics honesty
- **MTTR** needs both `detected_at` and `resolved_at`. If only the log-entry time exists, write "not measurable".
- **Money saved or lost** needs a measured before and after. Otherwise leave it out.

## Runbook template

```markdown
# <Alert name>
**Owner:** <team>   **Severity:** page | ticket   **Last verified:** <date>

## What this means
One sentence on user impact.

## Check first (2 minutes)
1. <command> — expected: <output>; if not, go to <step>

## Likely causes and fixes
| Signal | Cause | Fix (exact command) | Risk |
|---|---|---|---|

## Escalate if
<condition> → <who/how>

## Rollback / safe stop
```
A runbook step must be runnable by someone paged at 3 a.m.: exact commands, expected output,
and a decision at each step. Remove steps nobody has tested; mark untested ones `UNTESTED`.

## Do not
- Name a root cause that was not tested; write "most likely" and list what would confirm it.
- Invent timestamps, numbers or impact. Use `unknown`.
