---
name: analyzing-billing-exports
description: Analyze real cloud billing data files (AWS CUR or Data Exports CSV, GCP BigQuery billing export, Azure Cost Management export) with a bundled script that gives exact, reproducible numbers. Use whenever the user has a billing or cost export file (csv, jsonl) and asks why the bill went up, what drives spend, total for a month, whether this month is on track, idle or orphaned spend, one-off spikes, cost by tag or environment, or untagged spend. Do not estimate from memory or sample rows by eye: run the script. For general cost-saving advice without a data file use auditing-cloud-costs.
---

# Analyzing billing exports

Billing exports are large and full of traps (credits, tax, negation lines, partial months, messy tags).
Summing a column by hand or over a sample gives confident wrong answers. Use the script, then explain.

## Workflow

```
- [ ] 1. Identify the file, provider, period, and the question
- [ ] 2. Run the analyzer (read-only, offline, no dependencies)
- [ ] 3. Read the coverage and notes before any number
- [ ] 4. Answer from the script's numbers; cross-check anything surprising on the raw rows
- [ ] 5. Report facts, estimates and unknowns separately
```

**2. Run** (path relative to this skill's directory; resolve it first):
```bash
python3 scripts/analyze_billing.py EXPORT.csv --tag Environment        # human text
python3 scripts/analyze_billing.py EXPORT.csv --json > report.json     # for further processing
python3 scripts/analyze_billing.py EXPORT.csv --month 2026-09          # restrict to one month
```
It auto-detects AWS (CUR/Data Exports, `lineItem/...` or `line_item_...`), GCP (BigQuery export CSV/JSONL with
`credits`), Azure (`CostInBillingCurrency`) and a generic date+cost layout. It streams the file, so hundreds of MB are fine.
If detection fails, read the header and map columns (`references/export-formats.md`); do not guess.

**3. Always read first:** the `MONTHS` block (day coverage, `PARTIAL` flags, line-type breakdown) and the `NOTE` lines.

## Rules that prevent wrong answers
1. **Partial months.** If the latest month does not cover every day, never compare its total with a full month. Compare per-day averages or the projection, and say it is an estimate. "October is cheaper than September" from 12 days of data is the classic false saving.
2. **All line types count in an invoice total.** AWS: `Usage`, `SavingsPlanCoveredUsage` + `SavingsPlanNegation` (cancel each other), `SavingsPlanRecurringFee`, `Fee`, `Credit`, `Refund`, `Tax`. Filtering to `Usage` understates the bill; adding covered usage without the negation overstates it. State which definition you used (gross usage, net of credits, with tax).
3. **GCP:** `cost` is before credits; credits are separate (negative). Net = cost + credits.
4. **New cost lines vs growth.** In month-over-month drivers, a service|usage type that did not exist before is a different story (a launch, a misconfiguration) from the same line growing. Say which.
5. **Step change vs one-off.** A one-day spike and a sustained level shift need different fixes. The script labels them; confirm on the daily rows.
6. **Tags:** values differ by case and synonym (`prod`, `Prod`, `production`). Merge them explicitly and show the mapping; untagged spend is its own line, not distributed. The script case-folds only: merge synonyms yourself from its value list.
7. **Billing says cost, not state.** "Idle" lines (for example `PublicIPv4:IdleAddress`) are strong hints, but whether a disk or IP is attached must be confirmed in the cloud API/console before anything is deleted. Never delete from a billing file.
8. **Currency and discounts:** report the currency column; if a net/discounted cost column exists, say which one you used.
9. Billing data lags and can be revised; the last days are the least reliable.

## Answer format
- The number, the definition used (which lines, which period, which column), and the coverage (days present).
- Drivers as `service | usage type: +amount (share of the change)`, flagged NEW where applicable.
- Estimates (projections) labelled as such, with the method.
- What the file cannot tell you (attachment state, utilization, other accounts, discounts outside the file), and the next check to resolve it.

## Do not
- Print account IDs, resource IDs or tag values into public output without the user's say-so; this data is internal.
- Quote a total you did not compute with the script (or an equivalent full pass over the file).
- Turn the findings into savings promises: use `auditing-cloud-costs` to size savings from measurements.
