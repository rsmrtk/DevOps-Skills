---
name: designing-slo-alerting
description: Designs SLIs, SLOs, error budgets and burn-rate alerts, and reduces alert noise by alerting on symptoms instead of causes. Use when the user asks to define SLOs, write Prometheus alert rules, cut noisy alerts, close monitoring gaps, or build an early-warning system for a service.
---

# Designing SLOs and alerts

## 1. Pick the SLI first
An SLI is a ratio of good events to valid events, measured where the user feels it.

| Service type | SLI |
|---|---|
| Request/response | non-5xx responses / all responses; plus latency: requests under threshold / all |
| Pipeline / batch | runs finishing on time / scheduled runs; data freshness under threshold |
| Storage | successful reads+writes / attempts |

Decide what counts as "valid" (exclude health checks, known bad clients) and write it down.

## 2. Set the SLO and budget
`error budget = 1 - SLO`. 99.9% over 30 days = 43.2 min of full outage equivalent.
Choose the SLO from user need and current measured performance, not from a round number.
Measure for a few weeks before committing; an unmeasured SLO is a guess.

## 3. Alert on burn rate, multi-window
Alert when the budget burns fast enough to matter (Google SRE Workbook, 30-day window):

| Severity | Long window | Short window | Burn rate | Budget consumed |
|---|---|---|---|---|
| Page | 1h | 5m | 14.4 | 2% |
| Page | 6h | 30m | 6 | 5% |
| Ticket | 3d | 6h | 1 | 10% |

Both windows must exceed the threshold: the long one proves it matters, the short one proves it is still happening.

```promql
# SLO 99.9% => budget 0.001
(
  sum(rate(http_requests_total{code=~"5.."}[1h])) / sum(rate(http_requests_total[1h])) > (14.4 * 0.001)
)
and
(
  sum(rate(http_requests_total{code=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > (14.4 * 0.001)
)
```
Adjust the metric and labels to what the service actually exports; check with a query before shipping.

## 4. Reduce noise
For each existing alert ask: does a human have to act now? If not, it is a ticket or a dashboard, not a page.

- Alert on symptoms (errors, latency, freshness), not causes (CPU, restarts) — causes go on dashboards.
- Every page links a runbook and names the owner. No runbook, no page.
- Use `for:` to absorb blips, and inhibit child alerts when a parent fires.
- Review pages monthly: count pages per alert, delete or downgrade the top noisy ones, record the change.

## 5. Find gaps
List user-facing journeys and check each has an SLI and an alert path. A staging environment
benefits from the same SLIs with looser thresholds so problems appear before production.

## Do not
- Quote a "reduction in noise" without before/after page counts from the same period length.
- Propose an SLO number without stating the data it is based on.
- Alert on a metric you have not confirmed exists and has data.
