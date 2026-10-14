# Contributing

Thank you for helping. The most useful contribution is **a scenario where a skill gave a wrong or unsafe answer**.

## Workflow

1. Open an issue with the prompt, the answer you got, and what a careful operator would have done.
2. For a fix, add a failing case to the skill's `evals/evals.json` first, then change the skill so it passes.
3. Run the case with and without the skill. A change that does not move a result should not add text.

## Skill style

- Short `SKILL.md` (aim for under 100 lines). Put depth in `references/` and say when to read it.
- Description in the third person: what it does and when to use it, with the situations a user would actually describe.
- Explain *why* a rule exists instead of shouting it. Keep rules that change behaviour; drop restated textbook content.
- Default to read-only. Anything that mutates needs explicit approval written into the skill.
- No invented numbers: prices, savings and timings must come from data or be marked unknown.
- No secrets, customer data or internal hostnames in examples or fixtures.

## Scripts

- Offline, read-only, no network, standard library where possible.
- Never print secret values; say that a value was redacted.
- Exit codes: 0 clean, 1 findings of high severity, 2 usage or parse error.

## Validate before opening a PR

```bash
claude plugin validate .
claude plugin validate ./plugins/devops-sre
```
