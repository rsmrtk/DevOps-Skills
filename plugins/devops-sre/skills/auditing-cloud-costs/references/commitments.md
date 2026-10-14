# Commitments: Savings Plans, reservations, committed use

Commitments trade flexibility for a discount. They are financial purchases and mostly not reversible.
Never buy one without the owner's explicit approval and a documented usage baseline.

## The one rule
Commit to your **always-on minimum** over the last several months, not the average. Anything above the
commitment stays on-demand (or Spot) and can scale with demand. Over-committing pays for capacity you
do not use. Under-committing only leaves some discount on the table.

## Order of operations
1. Delete waste and fix storage/log retention (steps 1-3 of the ladder).
2. Rightsize (step 5). Otherwise the commitment locks in oversized capacity.
3. Measure the stable baseline per commitment scope (region, family, or spend per hour).
4. Buy in **layers** (for example a first slice now, more in a few months), so expiries are staggered and you can adapt.
5. Track **utilization** (share of the commitment used) and **coverage** (share of eligible usage covered). Low utilization means you over-bought; low coverage with high utilization means you can commit more.

## Choosing the type

| | AWS | GCP | Azure |
|---|---|---|---|
| Flexible spend commitment | Compute Savings Plan (any family, region, Fargate, Lambda) | Spend-based (flexible) CUD | Azure Savings Plan for compute |
| Specific-capacity commitment | EC2 Instance Savings Plan, Reserved Instances (Standard or Convertible) | Resource-based CUD (vCPU, memory, region) | Reservations (VM size and region, can be flexible within a size group) |
| Terms | 1 or 3 years, payment options (no/partial/all upfront) | 1 or 3 years | 1 or 3 years |
| Databases | RDS/ElastiCache/OpenSearch reserved instances, Database Savings Plans where offered | Cloud SQL / Spanner CUDs | Reserved capacity for SQL, Cosmos DB, and others |

- Flexible commitments cost a bit more than the most specific ones but survive migrations (instance family change, Graviton move, region change, containers). Prefer flexibility if you are modernising; prefer specific commitments for steady legacy fleets.
- 3-year terms give deeper discounts but assume the workload still exists, in the same shape, in 3 years. Be sceptical for fast-changing products.
- Upfront payment improves the discount but locks cash; compare with the cost of capital and your finance rules.
- Marketplaces and exchange rules differ (AWS Standard RIs can be resold on the RI Marketplace, Convertible RIs can be exchanged; Azure reservations can be exchanged or refunded within limits; GCP CUDs cannot be cancelled). Check current terms before purchase.

## Also consider before committing
- Enterprise discount programs / private pricing (EDP/PPA, MACC, GCP commit contracts): these are negotiated commitments on total spend and interact with plans.
- Is the workload moving to Spot, serverless, or another cloud? A commitment on it will strand.
- Are there active migrations or contract changes in the next 12 months?

## Report
Baseline (with the measurement window), proposed commit amount, expected utilization, the break-even
point, the exit/exchange options, and the sign-off needed. Label the savings `estimated` until the
first full billing period after purchase confirms them.
