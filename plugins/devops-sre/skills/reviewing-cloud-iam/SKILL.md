---
name: reviewing-cloud-iam
description: Review cloud access control for least privilege and privilege escalation on AWS (deep), GCP and Azure. Use whenever the user shares or asks about IAM policies, roles, trust policies, bucket or key policies, service accounts, GitHub Actions OIDC roles, cross-account access, "is this policy too permissive", wildcards, PassRole, AccessDenied debugging, unused permissions, or an access audit before production. Includes an offline AWS policy linter. Not for network security groups (use diagnosing-network-issues) or CI hardening (use hardening-github-actions).
---

# Reviewing cloud IAM

Access control is the blast radius of every other mistake. Review **what an identity can actually do**,
including by escalating, not only what the policy text says it does.

## Workflow

```
- [ ] 1. Scope: which account/project/subscription, which principal or policy, what is it for
- [ ] 2. Collect policies (read-only)
- [ ] 3. Lint, then reason about escalation and trust
- [ ] 4. Check real usage (what is granted but never used)
- [ ] 5. Report with the smallest safe fix
```

**2. Collect (read-only)** for AWS; GCP/Azure in `references/gcp-azure.md`:
```bash
aws iam get-role --role-name R                         # includes the trust policy
aws iam list-attached-role-policies --role-name R ; aws iam list-role-policies --role-name R
aws iam get-policy --policy-arn ARN ; aws iam get-policy-version --policy-arn ARN --version-id vN
aws iam get-role-policy --role-name R --policy-name P   # inline
aws iam list-entities-for-policy --policy-arn ARN       # who uses it
aws iam get-account-authorization-details > auth.json   # everything at once (large, sensitive: keep local)
```
Never paste credentials, access keys or session tokens into chat. Policy documents are fine to review, but
account IDs and ARNs are internal: keep them out of public output.

**3. Lint** (offline, read-only; path relative to this skill's directory):
```bash
python3 scripts/lint_iam_policy.py auth.json policies/ 
```
It reports full-admin and `NotAction` grants, escalation actions on `*` (PassRole, CreatePolicyVersion,
Attach*Policy, UpdateAssumeRolePolicy, CreateAccessKey, Lambda/EC2/SSM code execution), `Principal: *`,
OIDC trust without a tight `sub`, cross-account trust without conditions, confused-deputy gaps, broad write
on `Resource: *`. Findings are leads: confirm each in context. It does **not** see SCPs, permission
boundaries, session policies, resource policies it was not given, or actual usage; say so.

## What to reason about (a linter cannot)
1. **Evaluation logic:** an explicit Deny always wins; otherwise within one account an Allow in the identity policy **or** the resource policy is enough; **cross-account** access needs an Allow on **both** sides. SCPs and permission boundaries only restrict, they never grant. A missing permission is often a boundary or SCP, not the policy in front of you.
2. **Escalation paths:** can this identity become a more powerful one? Combinations matter: `iam:PassRole` + a compute action (`ec2:RunInstances`, `lambda:CreateFunction`, `ecs:RunTask`, `cloudformation:CreateStack`); policy-edit rights; `sts:AssumeRole` on `*`; `UpdateAssumeRolePolicy`; credentials creation for others. Full catalog in `references/aws-iam.md`.
3. **Trust policies:** who can assume this role, and under which conditions. Cross-account: ExternalId (third parties) or `aws:PrincipalOrgID`. GitHub Actions OIDC: pin `aud` **and** `sub` to `repo:ORG/REPO:ref:refs/heads/BRANCH` or `environment:NAME`; `repo:ORG/*` lets any repo in the org deploy to prod.
4. **Confused deputy:** service principals in resource policies need `aws:SourceArn`/`aws:SourceAccount`.
5. **Public access:** `Principal: *` on S3/SQS/SNS/KMS/Lambda/ECR needs a documented reason; check S3 Block Public Access and Access Analyzer external-access findings.
6. **Credentials:** long-lived access keys, old keys, root usage, no MFA for humans. Prefer roles, SSO/Identity Center, OIDC and short-lived credentials.
7. **Unused access:** granted ≠ needed. Use IAM Access Advisor and Access Analyzer unused-access findings; generate a least-privilege policy from CloudTrail activity instead of guessing.

## Fix principles (smallest safe change)
- Replace `*` actions with the list of actions the workload calls; replace `*` resources with ARNs; add Conditions (`aws:SourceArn`, `iam:PassedToService`, tags, `aws:PrincipalOrgID`, `aws:RequestedRegion`).
- Constrain `iam:PassRole` to specific role ARNs **and** `iam:PassedToService`.
- Separate duty: humans get time-bound, MFA-protected, audited access; workloads get narrow roles.
- Use permission boundaries and SCPs as guardrails for delegated administration, not as a substitute for narrow policies.
- Roll out restrictive changes safely: simulate first (`aws iam simulate-principal-policy`), watch CloudTrail for AccessDenied after the change, keep a tested rollback.

## Debugging AccessDenied
Read the error: it names the principal, action and resource. Then in order: identity policy allows it? explicit Deny anywhere? permission boundary? SCP? resource policy (cross-account)? session policy? condition keys (region, MFA, source IP/VPC, tags)? KMS key policy for encrypted resources? Decode authorization messages with `aws sts decode-authorization-message` when the error provides one.

## Report format
1. Scope reviewed and **not reviewed** (accounts, SCPs, boundaries, resource policies, usage data)
2. Findings by severity (Critical: admin or public/anonymous access or open trust; High: escalation path, broad trust; Medium: broad resources, missing conditions; Low: hygiene), each with the exact statement, why it matters, and the smallest fix
3. Escalation paths as chains (A can do X, which allows Y)
4. Changes needing approval, ordered by risk. Policy changes are never applied by this skill.

## Do not
- Create, modify or delete policies, roles, keys or bindings; propose them with a diff.
- Print secrets, access keys, tokens, or full account-wide authorization dumps into shared output.
- Call a policy "least privilege" or "safe" from the text alone; state which of SCP, boundary, resource policy and usage you did not see.
- Invent action names or condition keys: check the Service Authorization Reference for the service.
