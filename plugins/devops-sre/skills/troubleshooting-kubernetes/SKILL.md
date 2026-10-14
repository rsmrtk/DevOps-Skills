---
name: troubleshooting-kubernetes
description: Diagnoses failing Kubernetes workloads: CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled, failing probes, node pressure and stuck rollouts. Read-only by default. Use when a pod, deployment or node misbehaves, or the user pastes kubectl output or events.
---

# Troubleshooting Kubernetes

Read-only first. Confirm the context before any command: `kubectl config current-context`.
Never run a mutating command (`delete`, `apply`, `scale`, `set`, `rollout restart`, `drain`) without explicit confirmation.

## Triage in this order

```bash
kubectl get pods -n NS -o wide
kubectl describe pod POD -n NS            # Events at the bottom are the highest-value lines
kubectl get events -n NS --sort-by=.lastTimestamp | tail -20
kubectl logs POD -n NS -c CONTAINER --tail=100
kubectl logs POD -n NS -c CONTAINER --previous      # logs of the crashed instance
```

## Status → meaning → next check

| Status / signal | Usually means | Check |
|---|---|---|
| `Pending` | cannot schedule | `describe` → `FailedScheduling`: insufficient cpu/memory, taints, node selector, PVC unbound |
| `ImagePullBackOff` / `ErrImagePull` | bad tag, no registry auth, or rate limit | image name in spec, `imagePullSecrets`, registry reachability |
| `CrashLoopBackOff` | process exits repeatedly | `--previous` logs, exit code, config/secret refs, startup probe |
| `OOMKilled`, exit code 137 | container exceeded its **memory limit** | limit is too **low** for the workload (see below) |
| `Running` but not `Ready` | readiness probe failing | probe path/port, app start time, dependency down |
| `Terminating` forever | finalizer or stuck volume | `kubectl get pod -o yaml` → `finalizers`, node health |
| Rollout stuck | new pods not Ready or quota hit | `kubectl rollout status`, `describe deploy`, ResourceQuota |

## OOMKilled: the direction matters
OOMKilled means memory was **under**-provisioned or the app leaks. Do **not** advise lowering memory.
Check usage against the limit (`kubectl top pod --containers`, or the metrics backend), look at the
trend over time (flat near limit = raise limit; steady climb = leak), and compare requests vs limits.
State the direction explicitly in the answer: "under-provisioned" or "leak suspected".

## Exit codes
`0` clean exit (wrong command for a long-running service), `1` app error, `137` SIGKILL (OOM or forced), `139` segfault, `143` SIGTERM (graceful stop, fine during rollout).

## Nodes
```bash
kubectl get nodes; kubectl describe node NODE | sed -n '/Conditions/,/Addresses/p'
kubectl top nodes
```
`MemoryPressure`, `DiskPressure`, `PIDPressure` cause evictions; `NotReady` needs kubelet logs on the node.

## Rightsizing requests/limits
Only recommend a **reduction** with p95 CPU and peak memory over a window that includes normal peaks
and adequate metric coverage. On thin evidence, say so and recommend nothing. Never reduce for pods that crashed or were OOM-killed.

## Report format
1. Symptom (exact status/event text)  2. Evidence (commands run, what each showed)
3. Cause: confirmed / likely / unknown  4. Fix, with the exact command and its blast radius, awaiting approval.

## Do not
- Switch kubeconfig context or run `get-credentials` as part of diagnosis.
- Read Secret values (`kubectl get secret -o yaml` prints them). `describe secret` shows only key names and sizes.
- Verify a flag or subcommand from memory; check `kubectl <cmd> --help` when unsure.
