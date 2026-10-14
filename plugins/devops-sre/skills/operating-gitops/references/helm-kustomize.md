# Helm and Kustomize in GitOps

## Validate before merge (CI)
```bash
helm lint chart/ -f values/prod.yaml
helm template REL chart/ -f values/prod.yaml --namespace NS | kubeconform -strict -summary -ignore-missing-schemas
kustomize build overlays/prod | kubeconform -strict -summary -ignore-missing-schemas
kubectl diff -k overlays/prod          # needs cluster access; shows live vs rendered
helm diff upgrade REL chart/ -f values/prod.yaml   # helm-diff plugin
```
Render with the **same** Helm/Kustomize versions the controller uses (Argo CD and Flux bundle their own).
Add CRD schemas to the validator (or `-ignore-missing-schemas` and say so); an unvalidated CRD is "not checked", not "valid".

## Helm gotchas in a GitOps renderer
- The controller renders **without a cluster install**: `lookup` returns empty, `.Release.IsInstall` and hooks behave differently. Charts relying on `lookup` produce perpetual diffs or wrong output under Argo (`helm template`).
- `randAlphaNum`, `now`, `genCA` re-generate on every render: perpetual OutOfSync or rotating secrets. Pass fixed values.
- `Capabilities.APIVersions` checks may fail in template mode; supply `--api-versions` (Argo: `kubeVersion`/`apiVersions` settings).
- **CRDs** in a chart's `crds/` directory are installed once and **never upgraded or deleted** by Helm. Manage CRDs separately or via the controller's CRD policy.
- **Hooks** (`helm.sh/hook`) map to Argo hooks or run as Helm hooks under Flux; a failing hook blocks the release.
- Pin chart versions exactly (`1.2.3`), not ranges/`*`, so an upstream release cannot change prod unreviewed. Update by PR (Renovate/Dependabot).
- Values layering: later files win; keep a base `values.yaml` and one file per environment; check the effective values with `helm get values` / `helm template`, not by reading one file.
- OCI charts are immutable by digest; prefer digest pinning for critical charts.
- `helm rollback`/`history` apply to Helm-managed releases (Flux HelmRelease); under Argo, rollback is in Argo/Git.

## Kustomize gotchas
- **`commonLabels` changes selectors**: adding or changing it rewrites `spec.selector` of Deployments/StatefulSets, which is immutable, so the sync fails or forces recreation. Use `labels:` with `includeSelectors: false` for metadata-only labels.
- `namePrefix`/`nameSuffix` rewrite references it knows about (ConfigMap/Secret refs in pod specs); references in CRDs or annotations may not be updated: check the render.
- `configMapGenerator`/`secretGenerator` add a content hash to the name, which triggers a rollout when content changes (usually desired). `disableNameSuffixHash` removes it: then changes do not restart pods.
- Patch types: strategic merge (good for built-in kinds; lists merge by key) vs JSON 6902 (exact path; fails if the path does not exist). For CRDs strategic merge may replace lists wholesale.
- Remote bases: pin to a tag or commit (`?ref=v1.2.3`), never a branch, or upstream changes reach prod silently.
- `components` for reusable optional features; avoid deep chains of overlays that nobody can read. Prefer flat overlays: `base/` + `overlays/{dev,staging,prod}`.
- Run `kustomize build` with `--load-restrictor` defaults: files outside the kustomization root are blocked on purpose.

## Review the render, not the template
A one-line values change can add, delete or recreate resources. In PRs show the rendered diff (bot comment with `helm template`/`kustomize build` diff). Look for: removed resources (prune), changed selectors, changed `volumeClaimTemplates`, namespace changes, new cluster-scoped objects, `Secret` objects, replicas set to 0.
