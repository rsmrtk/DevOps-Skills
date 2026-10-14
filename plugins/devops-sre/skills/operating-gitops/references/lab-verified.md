# Behaviours verified on a live lab

Observed on a disposable kind cluster (Kubernetes v1.37, Argo CD v3.5.2, git served inside the cluster).
Argo CD and Kubernetes versions change messages and defaults: treat these as verified examples, not guarantees, and re-check on your version.

| Situation | What actually happened | Consequence / what to do |
|---|---|---|
| Commit pushed, nothing changes | Argo kept showing `Synced` to the old revision until a refresh; default polling is about 3 minutes | `argocd app get APP --hard-refresh` (or configure a webhook). Do not conclude "Argo ignores my commit" within minutes |
| Path or revision wrong | `Sync Status: Unknown`, **Health: Healthy**, condition `ComparisonError ... app path does not exist` | Health describes existing live resources; it does not mean the app works. Read conditions |
| Manual `kubectl scale` on an app with `selfHeal: true` | Replicas were reverted within seconds | Manual changes do not stick. Use the break-glass procedure (disable auto-sync, fix, commit, re-enable) |
| Changing a Deployment `spec.selector` | Sync did not fail once: operation stayed `Running` with `field is immutable ... Retrying attempt #N`; the app showed `OutOfSync` | Selector is immutable. Recreate deliberately (understand downtime) or keep the selector stable. Retries keep hitting the same error |
| Fixed Git after such a failure | App later showed `Synced` and `Healthy` while the **old operation was still `Running`** retrying the old revision (its Sync Revision unchanged) | After fixing Git, check `argocd app get APP --show-operation`; if a stale operation lingers, terminate it (`argocd app terminate-op APP`, approval needed) and let auto-sync start fresh. Green status alone is not proof |
| `argocd app rollback` with auto-sync on | `rpc error: code = FailedPrecondition desc = rollback cannot be initiated when auto-sync is enabled` | Use `git revert`. History IDs come from `argocd app history APP` |
| PreSync hook Job exits 1 | Nothing from the app was deployed: `OutOfSync`, **Health Missing**, operation `Running ... Retrying attempt #N` | The hook blocks the sync. Read the hook pod logs, fix the hook in Git. Use `hook-delete-policy` so stale hook objects do not collide |
| PVC with no consuming pod (StorageClass binding mode WaitForFirstConsumer) | Application `Synced` but **Progressing** indefinitely; PVC `Pending` | Not an Argo fault. Create the workload that mounts it, or accept it; check the StorageClass binding mode |
| Remove a PVC manifest from Git with `prune: true` | The live PVC was deleted on the next sync | Prune deletes data-bearing objects. Add `argocd.argoproj.io/sync-options: Prune=false`, take a backup, review deletions |
| Custom resource whose CRD is not installed | `one or more synchronization tasks are not valid: failed to discover server resources for group version ...: the server could not find the requested resource`, retried | Install the CRD first (separate app / sync wave / bootstrap). CRD and CR **in the same app** synced fine here because Argo orders CRDs before custom resources |
| Destination namespace missing | `namespaces "X" not found`, retrying; app `OutOfSync` | Add `CreateNamespace=true` sync option or define the Namespace in Git |
| App in a restricted AppProject | `Sync Unknown`, condition `InvalidSpecError` listing **both** a destination mismatch and a repo that is not in `sourceRepos` | Fix the Project or the Application narrowly. Read all conditions, there can be more than one |
| `kubectl delete application` without the finalizer | Application removed, **deployed resources stayed** (orphaned) | Default Applications created from manifests have no finalizer unless you add `resources-finalizer.argocd.argoproj.io` |
| Delete an Application with that finalizer | The managed ConfigMap was deleted with it | Check `metadata.finalizers` first. To keep resources use a non-cascading delete (`argocd app delete APP --cascade=false`) or remove the finalizer, then delete |

Lessons that cut across these cases: read conditions and the **operation** state, not only Sync/Health;
verify the revision Argo evaluated; and treat "Synced + Healthy" as a claim to confirm against the operation and the live objects.
