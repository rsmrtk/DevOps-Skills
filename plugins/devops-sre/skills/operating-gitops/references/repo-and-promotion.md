# Repo structure, promotion, secrets, recovery

## Repository layout
- **Separate application code from deployment config** (different repos or clearly separated paths): CI builds and tests code; the config repo records what runs where. Config changes should not rebuild images.
- One directory per environment (overlays or values files), **not long-lived branches** per environment: branches drift, diffs between envs are unreadable and merges conflict.
- Platform stack (ingress, cert-manager, operators, CRDs) in its own path/Application with explicit ordering before apps (sync waves or Flux `dependsOn`).
- Bootstrap: one root (app-of-apps / Flux bootstrap Kustomization) from which the rest of the cluster is reconstructed. A new cluster should be reproducible from Git plus a handful of out-of-band secrets.

## Promotion between environments
1. CI builds an immutable image (tag with commit SHA or digest).
2. A PR (or automation) bumps the tag in `dev`; after checks pass, the same artifact is promoted to `staging`, then `prod` by PR/approval. Promote the **artifact**, never rebuild per environment.
3. Never `latest` or mutable tags: a pod restart would silently change the version.
4. Automation options: CI opens PRs (Renovate, scripts); Argo CD Image Updater (git write-back); Flux image automation. Keep prod behind a human-approved PR.
5. Progressive delivery for risk: Argo Rollouts or Flagger (canary/blue-green with metric analysis) on top of the GitOps controller.

## Secrets
Never commit plaintext (including base64 `Secret`: it is not encryption). Pick one pattern:

| Pattern | How | Notes |
|---|---|---|
| SOPS + age/KMS | Encrypted values in Git, decrypted in cluster | Flux supports it natively; Argo CD needs KSOPS/plugin. Back up the age key offline |
| Sealed Secrets | Controller key in cluster, `SealedSecret` in Git | Key loss means re-sealing everything; back up the controller key; sealed to a cluster/namespace |
| External Secrets Operator | Git holds a reference; values live in Vault/AWS SM/GCP SM/Azure KV | Best for rotation and audit; needs the store to be available |
If a secret was ever committed: rotate it (history rewrite does not un-leak it).

## Rollback and recovery
- **Rollback = `git revert` the change** and let the controller apply it; the history stays truthful. Argo's own rollback needs auto-sync off and leaves Git out of date.
- Stateful data is not in Git: use backups (Velero, database-native) and **test restores**.
- Cluster loss: recreate the cluster, bootstrap the controller from Git, restore secrets keys (SOPS/sealed), restore PV data. Keep the runbook and rehearse it.
- Back up the GitOps controller's own configuration as code (Argo CD `argocd-cm`, RBAC, repo/cluster secrets handled via secret management), not only apps.

## Governance and safety nets
- Branch protection and CODEOWNERS on the config repo; required review for `prod/`. Signed commits where feasible.
- PR checks: render + schema validation, policy checks (Kyverno/OPA/conftest: no `latest`, resource requests, no privileged, required labels), secret scanning.
- Controller permissions follow least privilege: AppProjects/tenants, namespaced ServiceAccounts, no shared cluster-admin.
- Alerting: failed syncs, long OutOfSync/NotReady, Git source fetch failures, controller restarts.
- Define who may use break-glass (suspend, fix, commit, resume) and review each use.
