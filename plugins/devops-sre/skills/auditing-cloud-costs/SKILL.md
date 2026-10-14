---
name: auditing-cloud-costs
description: FinOps for AWS, GCP, Azure and Kubernetes: audit spend, explain a surprise bill, and find savings that do not cost performance or reliability. Use whenever the user wants to cut or understand cloud costs, asks whether a resource is worth keeping, plans Savings Plans, reservations or committed use, rightsizes workloads, reduces Kubernetes or data-transfer or logging cost, or asks how to save money on a cloud or cluster without hurting production. Holds provider-specific depth in references for AWS, GCP, Azure and Kubernetes.
---

# Cloud cost optimization (FinOps)

Goal: lower the bill without lowering what users experience. Every lever below has a risk level;
work from the safest to the riskiest and stop when the budget goal is met.

## Rule 1: inventory everything before promising anything
Savings computed for the one service you are working on miss the machine running next door.
Enumerate **every** project/account/subscription under the billing account first, every region.
If an enumeration fails (API disabled, no permission), list it under **not checked**, never as clean.

Start from the bill, not from guesses: group cost by service, then by account/project, then by usage
type. The top 3 lines usually hold most of the money. Provider details: `references/aws.md`,
`references/gcp.md`, `references/azure.md`.

## Rule 2: know how each cloud bills
- The invoice arrives after the fact. Deleting a resource on the last day of the month does not reduce that month's bill. Say this out loud.
- **Azure:** a VM in state `stopped` still pays for compute; only `deallocated` stops the meter.
- **GCP:** there is no cost API without a BigQuery billing export, and the export has no backfill. Check whether it is enabled before promising cost analysis.
- Orphans that keep billing: unattached disks, snapshots, unused static/public IPs, idle load balancers, NAT gateways, old images, container registries, log groups that never expire.
- Prices, free tiers and discount percentages change. Look up the current price list for the region
  before quoting a number; otherwise say "unknown".

## Rule 3: size savings from measurements
A saving counts only with a measured **before**, a measured **after**, and confounders checked
(deploys, traffic changes, seasonality). Otherwise label it `pending measurement`.
Use p95 (CPU) and peak (memory) over a window that includes normal peaks (at least 2 weeks, a
month-end or batch cycle if one exists); refuse to cut on a short window or low metric coverage.

## The savings ladder (safest first)

| Step | Lever | Risk | Typical examples |
|---|---|---|---|
| 1 | Delete waste | none, if confirmed unused | unattached disks, old snapshots, idle IPs/LBs/NAT, stopped-not-deallocated VMs, empty clusters |
| 2 | Stop paying for retention nobody reads | low | log retention and ingestion, storage lifecycle and tiering, old backups, metric cardinality |
| 3 | Cheaper equivalent | low | disk type (gp2 to gp3), newer instance generation, ARM/Graviton after testing, right storage class |
| 4 | Commit to the stable baseline | financial lock-in | Savings Plans, reservations, committed use discounts. See `references/commitments.md` |
| 5 | Rightsize | medium | CPU/memory requests and instance sizes from measurements. See `references/kubernetes.md` |
| 6 | Spot / preemptible | medium | stateless, restartable, multiple instance types, graceful shutdown |
| 7 | Schedule non-prod | low | scale dev/test to zero outside working hours |
| 8 | Architecture | high | cross-AZ and egress reduction, caching, serverless vs always-on, multi-region trimming |

Order matters: commit **after** you clean up and rightsize, otherwise you lock in waste.

## Guardrails: how to save without losing productivity
- Tie every change to a watch metric (latency, error rate, SLO burn; see `designing-slo-alerting`).
  Roll out to non-prod first, then one prod slice, then the rest. Write the rollback before the change.
- Never touch memory of a pod that was OOM-killed (exit 137, reason `OOMKilled`): it is **under**-provisioned.
- Do not cut stateful or single-replica components for savings without a backup and an owner's yes.
- Keep headroom for traffic spikes and failover: N+1 capacity, and autoscaler max not set to the current size.
- Developers' time costs more than most savings: skip changes that save little and add toil.
- Savings from dev/test must not block deploys (scheduling that breaks CI is not a saving).
- Cost tools (OpenCost/Kubecost, Cost Explorer) attribute spend; reconcile with the billing source.

## Prevent the bill from coming back
- Mandatory tags/labels (owner, env, cost-center) enforced by policy; untagged spend is reviewed weekly.
- Budgets with alerts per account/project at 50/80/100% actual and forecast; anomaly detection on.
- A monthly review: top 10 cost movers, who owns each, decision recorded.
- Unit cost (cost per request, per customer, per pipeline run) beats total cost for judging efficiency.

## Report format
1. Checked scope (accounts/projects/regions) and **not checked** scope
2. Findings: resource, evidence (age, last start/stop, attachment state, utilization), monthly cost *if known*
3. Savings: measured / estimated (state method) / pending measurement, with risk level from the ladder
4. Actions needing approval, ordered by risk. Deletion is never done by this skill without explicit confirmation.

## Commands are templates
CLI flags change between versions. The commands in the references were written from documentation, not
verified against your account: check `--help`, run read-only calls first, and state which you could not run.

## Do not
- Quote a currency figure you did not derive from billing data or a price you looked up; say "unknown" instead.
- Delete, stop, resize or purchase anything. Propose it with the evidence. Purchases of commitments are not reversible.
- Recommend a commitment sized to average usage; size it to the always-on minimum.
