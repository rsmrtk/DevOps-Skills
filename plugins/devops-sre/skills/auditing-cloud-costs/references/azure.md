# Azure cost reference

Read-only commands are templates; check `--help`. Many use Azure Resource Graph (`az extension add --name resource-graph`).

## Where the money is: find it first
- **Cost Management + Billing**: cost analysis grouped by subscription, resource group, service, tag; **exports** to storage for analysis; **budgets** with action groups. Tag inheritance and Azure Policy to enforce tags (`owner`, `env`, `cost-center`).
- **Enumerate every subscription** under the tenant (management groups) and query across them with Resource Graph:
  ```bash
  az account list --query "[].id" -o tsv
  az graph query -q "Resources | where type =~ 'microsoft.compute/disks' and properties.diskState == 'Unattached' | project name, resourceGroup, subscriptionId, sku.name, properties.diskSizeGB"
  az graph query -q "Resources | where type =~ 'microsoft.network/publicipaddresses' and isnull(properties.ipConfiguration) | project name, resourceGroup, subscriptionId, sku.name"
  ```
- **Azure Advisor** cost recommendations (rightsize/shut down VMs, reservations):
  ```bash
  az advisor recommendation list --category Cost
  ```

## Virtual machines
- **`stopped` still bills compute; `deallocated` does not.** A VM shut down from inside the OS stays allocated and billed. Find them:
  ```bash
  az vm list -d --query "[?powerState=='VM stopped'].[name,resourceGroup]" -o table
  ```
  Deallocate with `az vm deallocate`. Disks, public IPs and licenses keep billing when deallocated.
- **Azure Hybrid Benefit:** reuse Windows Server, SQL Server (and supported RHEL/SUSE subscriptions) licenses to drop the license part of the price. Confirm licensing eligibility with the owner; it is a legal/contract matter.
- **Reservations and Savings Plan for compute** (see `commitments.md`); Spot VMs for interruptible work (eviction policy, max price); Dev/Test subscription pricing for non-prod; **auto-shutdown** schedules on dev VMs.
- Rightsizing from Azure Monitor metrics (and Advisor): memory metrics need the agent. B-series burstable for light workloads; newer generations and Arm (Cobalt/Ampere) VM families often cost less per unit of work, test before moving.
- VM Scale Sets: autoscale in and out on real metrics; set min instances honestly.

## Disks and storage
- **Managed disks bill for provisioned size/tier**, even if barely used. Delete unattached disks and old snapshots; use incremental snapshots; move non-prod from Premium SSD to Standard SSD; consider Premium SSD v2/Ultra only where IOPS require it.
- **Blob access tiers:** Hot, Cool, Cold, Archive, with **early deletion fees** (Cool 30 days, Cold 90, Archive 180). Use lifecycle management policies to tier and delete; reserved capacity for large stable data.
- Redundancy (LRS/ZRS/GRS/RA-GRS) multiplies storage price; use GRS only where you need geo-redundancy.
- Unused storage accounts, file shares, and backup vault retention (Azure Backup instances, long retention, soft-deleted vaults).

## Networking
- Idle public IPs (Standard SKU static addresses bill even if unattached), idle Application Gateways / Load Balancers / VPN or ExpressRoute gateways / NAT Gateways / Bastion hosts, Azure Firewall (large fixed hourly cost: share one firewall via hub-and-spoke, use Basic/Standard SKU where adequate, deallocate in non-prod).
- Egress to the internet and between regions is billed; same-region traffic between availability zones may also be billed depending on current pricing. Use Private Link only where needed (hourly plus data processed).

## Kubernetes (AKS)
- **Free tier** control plane vs **Standard/Premium** tier (uptime SLA, billed per cluster hour): use Free for dev/test.
- Stop non-prod clusters out of hours (`az aks stop`); cluster autoscaler; **Spot node pools** for stateless workloads; node auto-provisioning (Karpenter-based) where available; right-size system node pools; shared clusters with namespace quotas rather than a cluster per team. See `kubernetes.md`.
- Container Insights ingests a lot into Log Analytics by default; tune data collection rules.

## Databases and platform
- **Azure SQL:** serverless with auto-pause for intermittent dev workloads, elastic pools for many small databases, reserved capacity for steady ones; vCore with Hybrid Benefit.
- **Cosmos DB:** autoscale throughput or serverless where traffic is bursty; RU over-provisioning is the top cost driver; use TTL.
- **App Service:** consolidate apps onto fewer plans; scale down plans in non-prod; delete empty plans (they bill with zero apps).
- **Functions Premium** keeps pre-warmed instances billing; use Consumption/Flex where cold starts are acceptable.

## Log Analytics / monitoring
- Ingestion per GB dominates. Options: commitment tiers when ingestion is steady and high, Basic/Auxiliary log plans for verbose low-value tables, filter at the source with data collection rules, set a **daily cap** carefully (it drops data once reached), reduce retention (long retention is billed beyond the included period).
- Check which workspaces ingest the most and which tables:
  ```kusto
  Usage | where TimeGenerated > ago(30d) | summarize GB = sum(Quantity)/1000 by DataType | sort by GB desc
  ```

## Idle resources checklist
Unattached disks, old snapshots, stopped-not-deallocated VMs, idle public IPs, idle gateways/firewalls/Bastion, empty App Service plans, oversized Log Analytics ingestion, AKS clusters left running over weekends, unused reservations (check utilization), orphaned NICs and NSGs (free but clutter), forgotten dev/test subscriptions.
