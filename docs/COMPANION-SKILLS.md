# Companion skills

These skills are **not part of this repository**. They are third-party validators and generators that pair well with `devops-sre`: they run real linters, while `devops-sre` focuses on judgement, safety and analysis.

## Recommended: `akin-ozer/cc-devops-skills`

A collection of generator and validator skills for common DevOps file types, Apache-2.0 licensed: <https://github.com/akin-ozer/cc-devops-skills>.

Useful combinations:

| Task | Companion | `devops-sre` skill |
|---|---|---|
| Lint Terraform | `terraform-validator` | `reviewing-terraform-changes` (plan review) |
| Lint Kubernetes manifests | `k8s-yaml-validator` | `troubleshooting-kubernetes` |
| Lint Helm charts | `helm-validator` | `operating-gitops` |
| Lint GitHub Actions | `github-actions-validator` | `hardening-github-actions` (security) |
| Lint Dockerfiles | `dockerfile-validator` | n/a |
| Write and check PromQL | `promql-generator`, `promql-validator` | `designing-slo-alerting` |

Install only what you need; every installed skill adds a short description to the context. Review a skill's `scripts/` before using it: they execute on your machine.

## Tools the validators call

The companion validators shell out to standard tools. Install the ones you use:

```bash
brew install shellcheck hadolint actionlint kubeconform yamllint ansible-lint terragrunt prometheus checkov trivy
```

`promtool` ships with the `prometheus` formula. `tflint` is not in Homebrew core: install it from the project's own tap, which is third-party code you opt into:

```bash
brew tap terraform-linters/tap
brew install terraform-linters/tap/tflint
```

Cloud rulesets (AWS, GCP, Azure) are added per project with a `.tflint.hcl` and `tflint --init`. Release binaries are at <https://github.com/terraform-linters/tflint>.
