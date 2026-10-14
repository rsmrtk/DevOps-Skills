# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Marketplace renamed from `devops-sre-skills` to `devops-skills`. Install with `claude plugin marketplace add rsmrtk/DevOps-Skills` and `claude plugin install devops-sre@devops-skills`. The plugin name (`devops-sre`) and skill invocation (`/devops-sre:<skill>`) are unchanged.

### Added
- GitHub Actions CI: manifest and evals JSON validation, `SKILL.md` frontmatter checks, smoke tests of the bundled analyzers. Actions are pinned by commit SHA and the workflow has read-only permissions.
- `homepage` and `repository` in `plugin.json`.

## [0.1.0]

### Added
- Plugin `devops-sre` with eleven skills and the `devops-sre-engineer` agent.
- Offline analyzers: `lint_iam_policy.py`, `gitops_lint.py`, `analyze_billing.py`.
- Documentation: skills catalog, evaluation report, companion skills, contributing and security policies.
