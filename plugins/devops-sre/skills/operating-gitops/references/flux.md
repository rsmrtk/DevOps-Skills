# Flux reference

Read-only unless marked (approval needed). API versions differ by Flux release: check `flux version` and `kubectl api-resources | grep toolkit.fluxcd.io`.

## Inspect
```bash
flux check                                  # controllers and CRDs healthy
flux get all -A                             # sources, kustomizations, helmreleases with Ready
flux get sources git -A ; flux get sources helm -A ; flux get sources oci -A
flux get kustomizations -A
flux get helmreleases -A
flux events -A                              # recent events across objects
flux logs --all-namespaces --level=error    # controller errors
flux trace deployment/NAME -n NS            # which Kustomization/HelmRelease owns it
flux build kustomization NAME               # render locally what Flux would apply
flux diff kustomization NAME --path ./dir   # live vs local (read-only)
```

## Reading status
Every object has a `Ready` condition with a message: read `kubectl describe` / `flux get` for the reason. Chain: **Source (GitRepository/HelmRepository/OCIRepository) → Kustomization / HelmRelease → workloads**. A broken source makes everything downstream stale but not deleted.

## Reconcile and suspend (approval needed)
```bash
flux reconcile source git NAME                       # fetch now
flux reconcile kustomization NAME --with-source      # fetch + apply now
flux reconcile helmrelease NAME --force              # --force re-runs even if unchanged: understand effect first
flux suspend kustomization NAME ; flux resume kustomization NAME
```
While suspended, Flux does not revert manual changes: always `resume`, and commit the fix to Git first.

## Typical problems
- **`dependency 'X' is not ready`:** `spec.dependsOn` target failing; fix it first.
- **Kustomization health check times out:** `spec.wait`/`healthChecks` with `timeout` too short, or a real rollout failure. Look at the workload, not only Flux.
- **Source fetch errors:** wrong secret/deploy key, branch/ref, or URL. Credentials live in a Secret referenced by `secretRef`: never print it.
- **`prune: true`:** objects removed from Git are deleted. Protect stateful objects with the label/annotation `kustomize.toolkit.fluxcd.io/prune: disabled`. Deleting a Kustomization with prune enabled deletes its objects.
- **Server-side apply conflicts / field ownership:** another manager owns a field (`kubectl get -o yaml --show-managed-fields`). Decide which owner wins; do not use `force: true` as a reflex (it recreates objects that fail to patch).
- **HelmRelease:** configure `install`/`upgrade` `remediation` (retries, rollback on failure) and `spec.interval`. Failed upgrade with rollback leaves the old version running, so "Ready=False + app still works" is common. Chart CRDs: `install.crds` / `upgrade.crds` policy (`Create`/`CreateReplace`), because Helm does not upgrade `crds/` by default. Drift detection (`driftDetection.mode: enabled`) makes Flux revert manual changes to Helm-managed objects.
- **Postbuild substitutions** (`postBuild.substituteFrom`): a missing variable renders literally or empty; use defaults `${VAR:=default}` and check the render with `flux build`.
- **Suspended objects** are shown in `flux get`; check this before debugging anything else.

## Secrets
SOPS decryption is built into the kustomize-controller: `spec.decryption: {provider: sops, secretRef: {name: sops-age}}`. The private key lives only in the cluster Secret and in a secure offline backup; the repo holds ciphertext. Alternatives: Sealed Secrets, External Secrets Operator.

## Multi-tenancy and security
- Give each tenant Kustomization a `serviceAccountName` with namespaced RBAC (Flux impersonates it), instead of cluster-admin.
- Run controllers with `--no-cross-namespace-refs=true` so tenants cannot reference other namespaces' sources/secrets.
- Verification: signed commits/tags for GitRepository (`spec.verify`), cosign verification for OCI artifacts and Helm charts.
- Restrict who can edit the Flux system namespace and the bootstrap repo path.

## Image automation (optional controllers)
`ImageRepository` (scan registry) → `ImagePolicy` (semver/regex/alphabetical rules) → `ImageUpdateAutomation` (commits the new tag back to Git via a marker comment `# {"$imagepolicy": "ns:policy"}`). Promotion stays auditable because the change is a Git commit; point automation at non-prod, promote to prod by PR.

## Notifications
`Provider` + `Alert` objects send reconcile failures to chat/webhooks; also set Git commit status providers to surface deploy state on PRs.
