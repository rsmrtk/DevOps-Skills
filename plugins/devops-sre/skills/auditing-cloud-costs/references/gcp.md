# GCP cost reference

Read-only commands are templates; check `--help`.

## Where the money is: find it first
- **Billing export to BigQuery** (standard and detailed usage) is the only way to analyse cost by SKU in SQL. It has **no backfill**: enable it now, analysis starts from the enable date. Check whether it exists before promising analysis.
- Cost table in the console, reports grouped by project, service, SKU, label. Budgets and alerts per project; budget alerts do not stop spend unless you automate it.
- **Enumerate every project** under the billing account, and across the org with Cloud Asset Inventory:
  ```bash
  gcloud projects list --format="value(projectId)"
  gcloud asset search-all-resources --scope=organizations/ORG_ID \
    --asset-types=compute.googleapis.com/Disk,compute.googleapis.com/Address --format=json
  ```
- Recommender (Active Assist): idle VMs, idle disks/IPs, rightsizing, committed-use suggestions.
  ```bash
  gcloud recommender recommendations list --project=P --location=ZONE \
    --recommender=google.compute.instance.IdleResourceRecommender
  gcloud recommender recommendations list --project=P --location=ZONE \
    --recommender=google.compute.instance.MachineTypeRecommender
  ```

## Compute Engine
- **Discounts:** committed use discounts (resource-based per vCPU/memory, or spend-based flexible CUDs), automatic sustained use discounts only on some older machine families (not E2), Spot VMs for restartable work (provider documents a large discount; may be preempted at any time, no max runtime guarantee). See `commitments.md`.
- Machine families: E2/N2D/T2A (Arm) are cheaper options for suitable workloads; custom machine types and the rightsizing recommender avoid paying for unused memory.
- Stop/delete idle VMs; check run history with `lastStartTimestamp` and `lastStopTimestamp`:
  ```bash
  gcloud compute instances describe NAME --zone=ZONE --format="value(status,lastStartTimestamp,lastStopTimestamp)"
  ```
- **Orphans:** unattached persistent disks, snapshots (use snapshot schedules with retention, archive snapshots for cold ones), reserved-but-unused static IPs (idle external IPs cost more than attached ones), unused images, idle forwarding rules/load balancers.
  ```bash
  gcloud compute disks list --filter="-users:*" --format="table(name,zone,sizeGb,type)"
  gcloud compute addresses list --filter="status=RESERVED"
  ```
- Disks: pd-ssd to pd-balanced where IOPS allow; right-size disk capacity (you pay for provisioned size).

## Cloud Storage
- Classes with **minimum storage durations**: Standard, Nearline (30 days), Coldline (90), Archive (365). Early delete is billed for the remainder. **Autoclass** moves objects automatically; lifecycle rules for known patterns.
- Retrieval and operations charges on colder classes; avoid them for frequently read data. Watch egress and cross-region reads. Delete old object versions and incomplete multipart uploads via lifecycle.

## BigQuery (often the largest surprise)
- On-demand pricing bills **bytes scanned**; editions bill slot capacity. Pick by workload: steady heavy usage favours slots (with autoscaling), sporadic usage favours on-demand.
- Reduce scans: partition and cluster tables, **require partition filter**, select only needed columns (never `SELECT *`), preview with a dry run, set `maximum_bytes_billed` per query and project/user quotas.
  ```bash
  bq query --dry_run --use_legacy_sql=false 'SELECT ...'
  ```
- Storage: logical vs physical billing model (compressed data can be cheaper on physical); partitions untouched for 90 days drop to the long-term storage rate; expire old tables and partitions with `default_table_expiration`/partition expiration. Materialized views and BI Engine for repeated dashboards; scheduled queries that nobody reads.

## GKE
- **Autopilot** bills per pod resource requests (no idle node capacity, but requests must be right); **Standard** bills nodes (you own bin packing). Pick Autopilot when workloads are spiky or you do not tune nodes.
- Standard: cluster autoscaler with the `optimize-utilization` profile, node auto-provisioning, Spot node pools for stateless workloads, right-sized machine types, regional vs zonal clusters (regional adds cross-zone traffic and control-plane resilience).
- Vertical Pod Autoscaler in recommendation mode; GKE cost allocation to see namespace/workload cost; see `kubernetes.md`.
- One management fee per cluster after the free allowance; many tiny clusters multiply it.
- Cross-zone traffic is billed; use topology-aware routing where available.

## Networking
- Egress to the internet and between regions is billed; inter-zone traffic inside a region is billed as well. Network Service Tiers (Premium vs Standard) change egress price and routing.
- **Cloud NAT** charges per gateway/VM hour plus data processed; use Private Google Access so Google API traffic does not go through NAT.
- Cloud CDN / Cloud Armor / load balancer forwarding rules each have their own line items.

## Logging and monitoring
- **Cloud Logging:** ingestion is billed beyond the free monthly allotment per project; storage retention beyond the default is billed. Use **exclusion filters** and routing sinks to drop or redirect noisy logs (load balancer health checks, debug, audit data access you do not need), and shorter retention on non-prod buckets.
  ```bash
  gcloud logging buckets list --project=P
  gcloud logging sinks list --project=P
  ```
- Cloud Monitoring custom metrics are billed by volume; high-cardinality labels inflate cost. Managed Prometheus bills per sample ingested: tune scrape intervals and drop unused series.

## Serverless
- **Cloud Run:** request-based CPU billing suits spiky traffic, instance-based CPU suits constant load and background work; min-instances cost money while idle; concurrency settings change instance count; set max instances to cap runaway cost.
- Cloud Functions/Run: delete unused revisions and images in Artifact Registry (cleanup policies).

## Idle resources checklist
Unattached disks, snapshots, reserved static IPs, idle VMs and instance groups, forwarding rules without backends, Cloud SQL instances with near-zero load (stop or right-size; HA and read replicas double cost), old Artifact Registry images, BigQuery tables and scheduled queries nobody reads, log buckets with long retention, unused projects.
