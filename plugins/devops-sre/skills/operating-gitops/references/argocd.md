# Argo CD reference

Commands are read-only unless marked (approval needed). Verify flags with `argocd <cmd> --help` for your version.

## Inspect
```bash
argocd app list                                   # sync + health at a glance
argocd app get APP                                # source, revision, conditions, resources
argocd app get APP --show-operation               # last sync result and per-resource messages
argocd app diff APP                               # live vs desired (read-only)
argocd app manifests APP                          # what Argo rendered
argocd app history APP                            # deployed revisions
argocd app resources APP
kubectl -n argocd logs deploy/argocd-repo-server  # render/clone errors
kubectl -n argocd logs sts/argocd-application-controller   # sync/diff errors
```
`argocd app get --hard-refresh APP` clears the manifest cache (re-fetch and re-render): use when Git changed but Argo shows stale content. By default Argo polls Git about every 3 minutes; a webhook makes it immediate.

## Sync and health
- **Sync status:** Synced / OutOfSync / Unknown. **Health:** Healthy / Progressing / Degraded / Suspended / Missing / Unknown. Read both.
- Health is computed per resource type; for CRDs you may need a custom health check (Lua) or the app stays `Progressing`/`Unknown`.
- Sync phases and hooks: `PreSync`, `Sync`, `PostSync`, `SyncFail`. A hook Job that never completes blocks the sync. Use `argocd.argoproj.io/hook-delete-policy` (`HookSucceeded`, `BeforeHookCreation`) so old hook objects do not collide.
- **Sync waves** (`argocd.argoproj.io/sync-wave: "N"`) order resources inside one sync: CRDs and namespaces first (low/negative), apps later. Each wave waits for the previous to be healthy.

## Typical errors
- **`ComparisonError` / `failed to generate manifest`:** render failed. Reproduce with the same tool version and values (`helm template`, `kustomize build`). Check repo credentials and that the path/revision exists.
- **"CRD not found" on first sync:** the custom resource is applied before its CRD. Put CRDs in an earlier wave or a separate Application; `SkipDryRunOnMissingResource=true` is the targeted escape hatch.
- **"metadata.annotations: Too long" (client-side apply, large CRDs):** use `ServerSideApply=true` sync option.
- **Permanent OutOfSync due to controller-managed fields:** narrow `ignoreDifferences` (example below) plus `RespectIgnoreDifferences=true` so sync does not overwrite them. Typical cases: HPA-managed `/spec/replicas`, webhook-injected CA bundles, defaulted fields.
  ```yaml
  spec:
    ignoreDifferences:
      - group: apps
        kind: Deployment
        jsonPointers: [/spec/replicas]
    syncPolicy:
      syncOptions: [RespectIgnoreDifferences=true]
  ```
  Prefer fixing the source of truth (remove `replicas:` from the manifest when an HPA manages it).
- **`SharedResourceWarning`:** two Applications manage the same object; fix ownership.
- **"one or more synchronization tasks are not valid" / immutable field:** a change the API rejects. Do not `Replace` before you know it recreates the object.
- **Resource tracking:** Argo identifies owned resources by label or annotation (`application.resourceTrackingMethod`); the annotation method avoids label collisions with other tools. Changing the method re-labels everything: plan it.

## Policies and their consequences
- `automated.prune: true` deletes live resources removed from Git. `selfHeal: true` reverts manual changes. Together they make the cluster fully Git-driven: the safe prod stance, as long as stateful resources are protected (`argocd.argoproj.io/sync-options: Prune=false`) and changes are reviewed.
- `Replace=true` / `Force=true` delete-and-recreate: causes downtime for workloads; use per-resource, never globally.
- `PruneLast=true` removes obsolete resources only after the new ones are healthy.
- **Application finalizer** `resources-finalizer.argocd.argoproj.io`: deleting the Application cascades deletion of its resources. To remove the Application but keep resources, delete with non-cascading (`argocd app delete APP --cascade=false`) after checking.
- **Rollback:** `argocd app rollback` requires auto-sync disabled for that app. Prefer `git revert` and let Argo apply it.

## Projects and security
- `AppProject` limits `sourceRepos`, `destinations` (cluster + namespace), and cluster-scoped kinds (`clusterResourceWhitelist`/`namespaceResourceBlacklist`). Do not run tenants in `default`.
- RBAC (`argocd-rbac-cm`) per project/role; SSO instead of the local admin account (disable `admin` after setup).
- Repo credentials are Kubernetes Secrets in the `argocd` namespace: treat as secrets, read-only deploy keys, never in the app repo.
- Secrets in manifests: Argo does not decrypt SOPS by itself; use KSOPS/plugin, Sealed Secrets, or External Secrets Operator.

## ApplicationSet
- Generators: `list`, `cluster`, `git` (directories/files), `matrix`/`merge`, `pullRequest`. One template, many Applications.
- A generator bug can create or **delete** many Applications at once. Set `syncPolicy.preserveResourcesOnDeletion: true` for safety on prod sets, and consider `applicationsSync: create-update` to prevent deletions by the ApplicationSet controller.
- App-of-apps vs ApplicationSet: ApplicationSet for repeated patterns, app-of-apps for a curated list with distinct settings.

## Notifications and visibility
Argo CD Notifications (triggers `on-sync-failed`, `on-health-degraded`) to chat/webhook. Alert on prolonged OutOfSync (metric `argocd_app_info` with `sync_status`).
