---
name: hardening-github-actions
description: Use this skill for any security review of CI/CD pipelines that run on GitHub Actions: auditing .github/workflows files, hardening or securing a pipeline, finding what to fix, or answering whether fork PRs, secrets, or runners are safe. Covers unpinned actions, overly broad GITHUB_TOKEN permissions, script injection from untrusted PR/issue input, pull_request_target risks, self-hosted runner exposure, replacing static AWS/cloud keys with OIDC, and deploy gates. Trigger even when the user says only "CI pipeline" or "workflows" and mentions secrets, forks, runners, or hardening. Not for generic workflow authoring (matrix builds, caching), other CI systems (GitLab, Jenkins), or Terraform reviews.
---

# Hardening GitHub Actions

Audit in order of blast radius. Report each finding with file, line, risk and the fix.

## Workflow

```
- [ ] 1. Inventory workflows and triggers
- [ ] 2. Run automated linters
- [ ] 3. Manual checklist
- [ ] 4. Report findings by severity
```

**1. Inventory**
```bash
ls .github/workflows; grep -n "^on:" -A6 .github/workflows/*.yml
```

**2. Linters** (run those installed, state which were not):
```bash
actionlint            # syntax and expression errors
zizmor .github/       # security: injection, permissions, unpinned actions
```

**3. Checklist**

| Check | Bad | Fix |
|---|---|---|
| Token permissions | no `permissions:` (default may be write) | top-level `permissions: contents: read`, widen per job |
| Third-party actions | `uses: org/action@v3` | pin to full commit SHA, comment the tag; Dependabot updates it |
| Script injection | `run: echo "${{ github.event.pull_request.title }}"` | pass via `env:` and use `"$TITLE"` |
| `pull_request_target` | checks out and runs PR head code | never run untrusted code with secrets; use `pull_request` |
| Cloud credentials | long-lived keys in secrets | OIDC (`id-token: write`) with a role scoped to the repo/branch |
| Self-hosted runners | on public repos or shared with untrusted PRs | restrict to private repos, ephemeral runners |
| Deploy gates | deploy on any push | `environment:` with required reviewers, branch rules |
| Hang protection | no limits | `timeout-minutes`, `concurrency:` with cancel for non-deploy jobs |
| Workflow edits | anyone can change | CODEOWNERS on `.github/workflows/` |
| Secrets in logs | `set -x`, `env` dumps, debug on | remove; secrets are masked only if registered |

Injection-safe pattern:
```yaml
- name: Greet
  env:
    TITLE: ${{ github.event.pull_request.title }}
  run: echo "$TITLE"
```

**4. Report** — Critical (secret exposure, untrusted code with secrets), High (write token, unpinned
third-party), Medium (no timeouts, no CODEOWNERS), Low (style). Lead with the single worst finding.

## Do not
- Rewrite workflows wholesale; propose the smallest diff per finding.
- Pin to a SHA you did not resolve. Resolve with `gh api repos/OWNER/REPO/commits/TAG --jq .sha`
  and check it belongs to the intended tag.
- Claim a workflow is secure; say which checks passed and which were not run.
