---
name: operating-gitops
description: Operate, review and debug GitOps delivery with Argo CD, Flux, Helm and Kustomize. Use whenever the user mentions an app stuck OutOfSync, Progressing or Degraded, a failed sync or HelmRelease, a Flux Kustomization not ready, drift that keeps coming back, preview or diff before a sync, rollback, promoting a release between environments, structuring a GitOps repo or ApplicationSet, secrets in Git (SOPS, Sealed Secrets, External Secrets), or reviewing GitOps manifests for risk. Includes a read-only repo linter. Not for writing application Helm charts from scratch or CI build pipelines (use hardening-github-actions for CI security).
---

# Operating GitOps

Git is the desired state; the controller makes the cluster match it. The consequence that drives
every rule here: **a change made directly in the cluster is temporary or will be reverted, and a change
made carelessly in Git is applied to production automatically.** Review the render, not the diff of templates.

## Workflow

```
- [ ] 1. Identify the stack and scope (Argo CD or Flux, Helm or Kustomize, which cluster/app/env)
- [ ] 2. Read state (read-only)
- [ ] 3. Diagnose by layer: source → render → apply → health → drift
- [ ] 4. Fix in Git, preview the effect, then let the controller apply
- [ ] 5. Verify: synced to the expected revision AND healthy
```

Confirm the cluster/context and environment before anything else. Prod and non-prod often share one repo.

## Diagnose by layer (stop at the first broken one)

| Layer | Question | Argo CD | Flux |
|---|---|---|---|
| Source | Can the controller read the repo/chart/OCI and is it on the revision I expect? | `argocd app get APP` (revision, ComparisonError), repo-server logs | `flux get sources all -A`, `flux events` |
| Render | Does Helm/Kustomize produce valid manifests with these values? | `argocd app manifests APP`, `helm template`, `kustomize build` | `flux build kustomization NAME`, `flux diff` |
| Apply | Does the API server accept them (RBAC, CRDs, validation, webhooks, immutable fields)? | sync result, `argocd app get APP --show-operation` | `flux get kustomizations`, controller logs |
| Health | Do the workloads become ready (probes, quotas, image pulls, hooks)? | health status, `kubectl describe` | `flux get helmreleases`, `kubectl describe` |
| Drift | Is something else mutating the object (HPA, webhook, operator, humans)? | `argocd app diff APP` | `flux diff`, `kubectl get ... -o yaml` managedFields |

Know the two separate axes. Argo CD: **sync status** (does live match Git?) vs **health status** (is it working?).
`Synced + Degraded` means Git was applied and the app is broken; `OutOfSync + Healthy` means it runs but differs from Git.

## Common symptoms

| Symptom | Usual cause | Check |
|---|---|---|
| OutOfSync forever, diff shows fields you did not set | A controller or webhook mutates the field: HPA owns `replicas`, defaulted fields, injected sidecars, CA bundles | Read the diff; add a narrow `ignoreDifferences` (Argo) or fix the source of truth. Never ignore whole resources |
| ComparisonError / "failed to generate manifest" | Helm/Kustomize render fails, bad values, chart not reachable, repo auth | Render locally with the same version and values |
| Sync fails on a CRD or custom resource | CRD not yet applied (ordering), or CRD too large for client-side apply annotation | Sync waves / separate app for CRDs; server-side apply |
| Stuck `Progressing` | Rollout not ready: failing probe, missing image, quota, pending PVC, or a hook Job that never finishes | `kubectl describe`, events; see hooks |
| Stuck on a PreSync/Sync hook | Hook Job fails or hangs and blocks the whole sync | Hook logs, `hook-delete-policy`, backoffLimit |
| "immutable field" error | Selector/volumeClaimTemplate/Job spec changed | Recreate deliberately (understand the downtime), do not blindly `Replace` |
| Flux "dependency not ready" | `dependsOn` target failing | Fix the dependency first; read its status |
| HelmRelease failed then rolled back | Upgrade failed health checks; remediation reverted | `flux get hr`, helm history, pod events of the failed upgrade |
| Change merged but nothing happens | Polling interval, webhook missing, controller suspended, wrong branch/path | Check the observed revision and `suspend` state |

Details and commands: `references/argocd.md`, `references/flux.md`, `references/helm-kustomize.md`. Real observed symptoms and messages from a live lab: `references/lab-verified.md`.

## Making changes safely
1. **Preview first.** Render and diff before merging: `kustomize build` / `helm template` piped to a schema validator (kubeconform), `argocd app diff`, `flux diff kustomization`, or `kubectl diff`. Read the diff for deletes, replaced resources, selector changes and namespace moves.
2. **Know what prune does.** With pruning enabled, removing a manifest from Git **deletes** the live resource, including PVCs and databases. Protect stateful resources (`Prune=false` annotation in Argo, `kustomize.toolkit.fluxcd.io/prune: disabled` in Flux) and review deletions explicitly.
3. **Know what deleting the controller object does.** Deleting an Argo `Application` with the resources finalizer, or a Flux `Kustomization` with prune enabled, can delete everything it manages. Check the finalizer/prune setting before deleting; do not delete to "refresh".
4. **Roll out progressively:** non-prod first, one environment per PR, pinned versions. Argo rollback requires disabling auto-sync; the GitOps way is `git revert`.
5. **Break-glass procedure** for emergencies: suspend/disable auto-sync for that app, apply the fix, **commit the same fix to Git**, then resume. Otherwise the controller reverts it or the fix is lost.
6. **Never** `kubectl edit/patch` as the final fix, `--force`/`Replace=true` on prod without understanding recreation, or `--prune`/`--cascade` with a guessed scope.

## Review checklist for a GitOps repo or PR
Run the bundled linter first (read-only, offline, needs PyYAML):
```bash
python3 scripts/gitops_lint.py path/to/repo        # path relative to this skill's directory; resolve it
```
It flags plaintext Secrets, credentials in repo URLs, unpinned images and charts, `default` Argo project,
`commonLabels` (changes immutable selectors), `Replace`/`Force` sync options, and `prune` with `selfHeal` combinations.
Then check by hand what a linter cannot see:
- **Secrets:** never plaintext in Git. SOPS (Flux decrypts natively; Argo CD needs a plugin/KSOPS), Sealed Secrets, or External Secrets Operator. Rotate any secret that was ever committed. See `references/repo-and-promotion.md`.
- **Pinning:** chart versions, image tags (ideally digests), `targetRevision` for charts and third-party bases. No `latest`, no `*`.
- **Access:** Argo AppProjects restrict source repos, destinations and cluster-scoped kinds; Flux uses a ServiceAccount per tenant. Controllers do not hold cluster-admin for tenants that do not need it.
- **Environments:** directories/overlays per environment, not long-lived branches; promotion by PR.
- **Observability of the pipeline:** sync failures and out-of-sync duration alert someone (Argo notifications, Flux alerts/providers).

## Do not
- Sync, reconcile, suspend, resume, delete, or roll back without approval and a stated expected effect (read-only inspection is fine).
- Print Argo/Flux repository or cluster credentials, `Secret` contents, or decrypted values; `argocd repo list`/cluster secrets and `kubectl get secret -o yaml` expose them.
- Claim "fixed" until the app shows the expected revision, **Synced and Healthy** (or Flux `Ready=True`), and the symptom is gone.
- State API versions or field names from memory for your cluster: check `kubectl api-resources`, `argocd version`, `flux version`.
