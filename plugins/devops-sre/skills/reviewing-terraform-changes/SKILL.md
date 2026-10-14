---
name: reviewing-terraform-changes
description: Use this skill whenever a Terraform or OpenTofu plan is about to be applied, or the user wants a plan looked at, explained, or sanity-checked before it touches real infrastructure. Typical situations: pasting or pointing to a plan output and asking "is this safe?"; a plan shows resources to destroy or replace and the user is worried; a rename, move, or refactor makes Terraform want to destroy and recreate something (the fix is a moved block); reviewing a Terraform PR; deciding whether to run or approve an apply or destroy; import, state mv, or state rm; a stuck state lock or force-unlock; drift or refresh-only changes nobody made in code. Produces a safe / safe with conditions / blocked verdict. Not for installing Terraform, CI lint or formatting pipelines, writing new modules, general Terraform concepts, or converting from other IaC tools.
---

# Reviewing Terraform changes

The plan is the contract. Review what will happen, not what the diff looks like.

## Workflow

```
- [ ] 1. Static checks
- [ ] 2. Saved plan
- [ ] 3. Read destroys and replacements
- [ ] 4. State and blast radius
- [ ] 5. Verdict
```

**1. Static checks** (fix before planning):
```bash
terraform fmt -check -recursive && terraform validate
tflint 2>/dev/null; trivy config . 2>/dev/null   # run what is installed; say which were skipped
```

**2. Saved plan.** Never apply a plan you did not save and read.
```bash
terraform plan -out=tfplan
terraform show -json tfplan > plan.json
```

**3. Destroys and replacements** — the only lines that cause outages:
```bash
jq -r '.resource_changes[] | select(.change.actions | index("delete"))
       | "\(.change.actions|join("+"))\t\(.address)"' plan.json
```
`["delete","create"]` is a replacement. In the human plan, find `# forces replacement` and
name the attribute that forces it. Stateful resources (databases, disks, buckets, KMS keys,
DNS zones) that are deleted or replaced are blockers until the user confirms and a backup exists.

**4. State and blast radius**
- Which state/workspace/environment is this? A `prod` plan run from a `dev` directory is a finding.
- `-target` in a routine workflow is a smell: it skips dependencies and leaves state inconsistent.
- Resources without `lifecycle { prevent_destroy = true }` that hold data: recommend it.
- Secrets end up in state and in plan output. Mark sensitive; never paste plan JSON with values into chat.

**5. Verdict:** `safe` / `safe with conditions` / `blocked`, with the list of destroys and replacements
and the single reason for each. Do not say "looks fine" without having read the plan.

## State operations (always dry-think first)

| Intent | Command | Note |
|---|---|---|
| Rename/move in code | `moved {}` block | Preferred; reviewable in PR |
| Adopt existing resource | `import {}` block, then plan | Plan must show no changes after import |
| Stop managing, keep real resource | `terraform state rm` | Does **not** destroy; resource becomes unmanaged |
| Manual move | `terraform state mv` | Back up first: `terraform state pull > backup.tfstate` |

## Drift

```bash
terraform plan -refresh-only      # shows real-world changes without proposing config changes
```
Decide per item: update the code to match reality, or apply to revert reality. Say which.

## Do not
- Run `apply` or `destroy` without explicit user confirmation of the exact plan.
- Force-unlock a state lock without confirming nobody is running an apply.
- Claim a provider/resource attribute exists without checking the provider docs or `terraform providers schema`.
