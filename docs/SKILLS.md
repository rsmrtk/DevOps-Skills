# Skills catalog

Every skill is a short `SKILL.md` that loads when the skill triggers, plus optional `references/` (read on demand) and `scripts/` (offline analyzers). Invoke a skill explicitly with `/devops-sre:<skill>` or let the `devops-sre-engineer` agent route the task.

> Automatic triggering is unreliable for simple requests (recall measured at roughly 12-50%). Explicit invocation is the dependable path.

## Contents

- [Infrastructure and change safety](#infrastructure-and-change-safety): `reviewing-terraform-changes`, `reviewing-cloud-iam`
- [Delivery](#delivery): `hardening-github-actions`, `operating-gitops`
- [Reliability and observability](#reliability-and-observability): `designing-slo-alerting`, `troubleshooting-kubernetes`, `diagnosing-network-issues`, `operating-patroni-consul`, `writing-postmortems-and-runbooks`
- [FinOps](#finops): `auditing-cloud-costs`, `analyzing-billing-exports`

---

## Infrastructure and change safety

<details open>
<summary><b>reviewing-terraform-changes</b>: read the plan, not the diff</summary>

**Use when:** a Terraform/OpenTofu plan is about to be applied, resources would be destroyed or replaced, a rename needs a `moved` block, state operations (`import`, `state mv`, `state rm`), stuck locks, drift.

**Does:** static checks, saved plan, `jq` over `plan.json` for deletes and replacements, state and blast-radius questions, a **safe / safe with conditions / blocked** verdict.

**Rules:** never apply a plan you did not save and read; `state rm` does not destroy; force-unlock only after confirming no apply is running; never paste plan JSON with secrets into chat.

**Example prompts**
- "Here is the plan output. Can I apply it to prod?"
- "Terraform wants to destroy and recreate this database after I renamed the resource. Why?"
</details>

<details open>
<summary><b>reviewing-cloud-iam</b>: least privilege and escalation paths</summary>

**Use when:** reviewing IAM policies, roles, trust policies, bucket/key policies, service accounts, GitHub Actions OIDC roles, cross-account access, AccessDenied errors, or an access audit.

**Does:** collects policies read-only, runs the bundled linter, then reasons about what a linter cannot: evaluation logic (explicit deny, SCPs, boundaries, cross-account needs both sides), escalation chains, trust conditions, confused deputy, public access, unused permissions.

**Ships:** `scripts/lint_iam_policy.py`; `references/aws-iam.md` (evaluation logic, escalation catalog, trust patterns); `references/gcp-azure.md`.

**Rules:** proposes policy diffs and never applies them; never prints keys or tokens; does not call a policy "least privilege" from text alone.

**Example prompts**
- "Is this CI deploy role policy OK? It has `iam:PassRole` on `*`."
- "Review this GitHub OIDC trust policy. It uses `repo:acme/*`."
</details>

## Delivery

<details open>
<summary><b>hardening-github-actions</b>: security review of workflows</summary>

**Use when:** auditing `.github/workflows`, answering whether fork PRs, secrets or runners are safe, replacing static cloud keys with OIDC.

**Does:** inventory, `actionlint`/`zizmor` when installed, a checklist covering token permissions, SHA pinning, script injection, `pull_request_target`, self-hosted runners, deploy gates, timeouts, CODEOWNERS; findings by blast radius.

**Rules:** smallest diff per finding; pin only SHAs it resolved; never claims a workflow is "secure", only which checks passed.
</details>

<details open>
<summary><b>operating-gitops</b>: Argo CD, Flux, Helm, Kustomize</summary>

**Use when:** an app is OutOfSync, Progressing or Degraded, a sync or HelmRelease failed, drift keeps returning, you need a preview before a sync, rollback, promotion, repo structure, or secrets in Git.

**Does:** diagnoses by layer (source, render, apply, health, drift), a symptom table, rules for safe changes (preview, prune consequences, finalizer behaviour, break-glass), and a repo review checklist.

**Ships:** `scripts/gitops_lint.py`; references for Argo CD, Flux, Helm/Kustomize, repo structure and promotion, and `lab-verified.md` with behaviours recorded on a disposable kind cluster (for example: an auto-sync operation keeps retrying the old revision after Git is fixed; `prune` deletes PVCs).

**Rules:** no sync, delete, suspend or rollback without approval; never print repository or cluster credentials; "fixed" means expected revision, Synced and Healthy.
</details>

## Reliability and observability

<details>
<summary><b>designing-slo-alerting</b>: SLIs, SLOs, burn-rate alerts</summary>

**Use when:** defining SLOs, writing Prometheus alert rules, cutting noisy alerts, finding monitoring gaps.

**Does:** picks SLIs where users feel them, sets SLOs from measured data, multi-window burn-rate alerts (14.4 / 6 / 1), symptom-over-cause alerting, noise review with before/after page counts.
</details>

<details>
<summary><b>troubleshooting-kubernetes</b>: read-only triage</summary>

**Use when:** CrashLoopBackOff, Pending, OOMKilled, failing probes, node problems.

**Rules:** read-only; an OOMKilled pod is under-provisioned on memory.
</details>

<details>
<summary><b>diagnosing-network-issues</b>: layer by layer</summary>

**Use when:** a service is unreachable, slow, times out, or shows certificate errors.

**Does:** DNS, TCP, TLS, HTTP, MTU, and Kubernetes pod networking in order.
</details>

<details>
<summary><b>operating-patroni-consul</b>: HA Postgres on Patroni with Consul/Raft</summary>

**Use when:** failover timing, DCS quorum loss, ttl settings, Consul ACL for Patroni, `patronictl`.

**Notes:** distilled from a hands-on lab; the `loop_wait + 2*retry_timeout <= ttl` rule and the observed ~8 s graceful and ~25 s hard failover timings come from that lab's settings. `failsafe_mode` was not tested.
</details>

<details>
<summary><b>writing-postmortems-and-runbooks</b>: from evidence</summary>

**Use when:** after an incident, or when a procedure needs to be runnable by someone else.

**Does:** blameless postmortems built from notes and logs, no invented revenue or MTTR figures, runbooks with steps marked UNTESTED until someone ran them.
</details>

## FinOps

<details open>
<summary><b>auditing-cloud-costs</b>: how to save without losing performance</summary>

**Use when:** cutting cloud or cluster cost, understanding a surprise bill, planning Savings Plans or committed use, rightsizing, reducing data-transfer or logging cost.

**Does:** inventory everything first, know how each cloud bills (stopped vs deallocated, invoices arrive after the fact), size savings from measurements, and work down a **savings ladder** from safest to riskiest. Guardrails tie every change to a watch metric and a rollback.

**Ships:** `references/aws.md`, `gcp.md`, `azure.md`, `kubernetes.md`, `commitments.md`.

**Rules:** no currency figure without billing data or a looked-up price; commit to the always-on minimum, never the average; never delete, stop, resize or purchase.
</details>

<details open>
<summary><b>analyzing-billing-exports</b>: exact numbers from a billing file</summary>

**Use when:** you have a CUR, BigQuery export or Azure Cost Management file and ask why the bill rose, what drives spend, whether this month is on track, idle spend, spikes, or untagged cost.

**Ships:** `scripts/analyze_billing.py` (standard library only, streams large files) and `references/export-formats.md`.

**Catches:** partial months compared with full ones, totals that drop Savings Plan, credit or tax lines, new cost lines mistaken for growth, one-off spikes mistaken for step changes, messy tag values.

```bash
python3 plugins/devops-sre/skills/analyzing-billing-exports/scripts/analyze_billing.py export.csv --tag Environment
```
</details>
