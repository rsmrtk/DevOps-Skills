# Kubernetes cost reference (EKS, GKE, AKS, self-managed)

Cluster cost = nodes (compute, disks, network) + control plane + load balancers + storage + observability.
The scheduler places pods by **requests**, so requests, not usage, decide how many nodes you pay for.

## 1. Measure before touching anything
- Per workload: CPU p95 and memory peak over at least 2 weeks versus requests. Usage/requests ratio per namespace shows where the slack is.
- Tools: Prometheus (`container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `kube_pod_container_resource_requests`), Vertical Pod Autoscaler in **recommendation-only** mode (`updateMode: "Off"`), Goldilocks, OpenCost/Kubecost for attribution, cloud-native cost allocation (GKE cost allocation, EKS split cost allocation, AKS cost analysis).
- Node-level: allocatable vs requested vs used. Large requested-but-unused slack means rightsizing wins; high requested and high used means you are efficient.
  ```bash
  kubectl top nodes; kubectl describe nodes | grep -A8 "Allocated resources"
  kubectl get pods -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,CPU_REQ:.spec.containers[*].resources.requests.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory
  ```

## 2. Rightsize requests and limits (medium risk)
- Set **memory request = memory limit**: memory is not compressible, so a pod over its limit is OOM-killed and an unbounded one can hurt neighbours. Add 15-30% headroom over observed peak.
- **CPU:** set requests from p95 usage; many teams leave CPU limits off to avoid throttling while keeping requests, since limits throttle even when the node has spare CPU. Decide as a team and document it.
- Never lower the memory of a pod that was `OOMKilled`; raise it.
- Change in small steps (for example 20-30% at a time), one workload at a time, watching latency, error rate and restarts. Keep the previous values for rollback.
- Use `LimitRange` defaults and `ResourceQuota` per namespace so new workloads do not appear with giant requests.
- JVM/.NET/Go: align heap and `GOMEMLIMIT` with the container limit, or the runtime and the kernel disagree.

## 3. Autoscaling and packing (the largest steady lever)
- **HPA** on the metric that reflects load (requests per second, queue depth through KEDA), not only CPU. Set `minReplicas` to what failover needs, not 10 out of habit.
- **Node autoscaling:** Cluster Autoscaler or **Karpenter** (AWS, also Azure node auto-provisioning) with consolidation, so underused nodes are drained and removed. GKE: `optimize-utilization` autoscaling profile or Autopilot.
- Make consolidation safe: **PodDisruptionBudgets** on every replicated service, `terminationGracePeriodSeconds` enough for graceful shutdown, readiness probes, and no `safe-to-evict: "false"` annotations unless required.
- **Node sizing:** very small nodes waste capacity on DaemonSets and kubelet reservations; very large nodes increase blast radius and make bin packing coarse. A mixed pool of a few sizes lets the autoscaler pack well.
- Fix what blocks packing: pods with anti-affinity everywhere, topology spread too strict (`DoNotSchedule` where `ScheduleAnyway` would do), huge requests relative to node size, per-pod local disks.
- **Vertical Pod Autoscaler** in `Auto` mode restarts pods to resize them: use it for stateless workloads with PDBs, recommendation mode elsewhere.

## 4. Spot / preemptible nodes (medium risk, large saving)
- For stateless, restartable, replicated workloads: batch, CI runners, web tiers with several replicas.
- Use many instance types/families and several zones so capacity pools are deep; keep an on-demand base pool for system components and stateful or single-replica services.
- Handle interruption: node termination handler (AWS), graceful shutdown, PDBs, topology spread across zones.
- Do not put databases, leaders without failover, or anything with long unsaved state on Spot.

## 5. Schedule non-production
- Scale dev/test namespaces to zero outside working hours (KEDA cron scaler, `kube-downscaler`, CronJobs patching replicas) and let the node autoscaler remove the nodes.
- Stop whole non-prod clusters over weekends where the provider supports it (AKS stop, node group scale to zero).
- Ensure CI is not blocked: warm up before the workday, exclude shared tooling.

## 6. Architecture and hidden costs
- **Cross-AZ traffic** between services is billed on most clouds. Use topology-aware routing / traffic distribution (`PreferClose` where supported), keep chatty pairs in the same zone when availability allows.
- **Egress and NAT:** pull images through an in-region registry/pull-through cache; private endpoints for cloud APIs so they do not traverse NAT.
- **Load balancers:** every `Service type=LoadBalancer` is a cloud LB with an hourly cost. Share ingress controllers, delete orphans after namespaces are removed.
- **Storage:** orphaned PVs (reclaim policy `Retain`) and snapshots after workloads are deleted; oversized PVCs (cannot shrink; recreate). Use the cheapest storage class that meets IOPS.
- **Observability:** Prometheus metric cardinality, log volume per pod, tracing sampling. These often cost more than the nodes they watch. Drop unused series, shorten retention, sample traces.
- **Cluster sprawl:** each cluster carries control-plane fees and system pods. Prefer fewer shared clusters with namespace isolation where the security model allows.
- Arm nodes: build multi-arch images and move stateless services first (test performance).
- Old Kubernetes versions on managed services can attract extended-support charges.

## 7. Guardrails (productivity first)
- Define the constraint as an SLO (see `designing-slo-alerting`): savings are only accepted while latency and error SLOs hold and the error budget is not burning faster than normal.
- Canary every change; keep the rollback one command away; never change many workloads at once.
- Keep N+1 headroom and autoscaler maximums above current size.
- Review weekly the list of workloads with the largest request/usage gap and assign owners; the team that owns the code decides its numbers.
- Report savings as `measured` only after comparing a stable before/after window.

## Quick wins by risk
No risk: orphan PVs/LBs/snapshots, empty namespaces, stale images. Low: log retention, non-prod schedules, storage class. Medium: requests rightsizing, Spot for stateless, consolidation. High: node-size or architecture changes, multi-cluster merges.
