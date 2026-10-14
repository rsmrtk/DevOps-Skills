# AWS IAM reference

## Policy evaluation (same account)
1. Explicit **Deny** in any applicable policy (identity, resource, boundary, SCP, session): denied.
2. Organization **SCPs** must allow it (they filter, never grant).
3. **Resource-based policy** Allow can grant to a principal in the same account without an identity policy (exception: some services, and cases where the resource policy names a role session/assumed-role principal).
4. **Permission boundary** (if set on the user/role) must allow it.
5. **Session policy** (if used) must allow it.
6. **Identity-based** policy Allow.
Cross-account: both the identity policy in the caller's account and the resource policy (or assumed role trust + role policy) in the target account must allow.

## Privilege escalation catalog (on a wildcard or too-broad resource)
- `iam:CreatePolicyVersion`, `iam:SetDefaultPolicyVersion`: rewrite or re-activate a policy attached to oneself.
- `iam:AttachUserPolicy` / `AttachRolePolicy` / `AttachGroupPolicy`, `iam:PutUserPolicy` / `PutRolePolicy` / `PutGroupPolicy`: grant admin to self.
- `iam:UpdateAssumeRolePolicy` + `sts:AssumeRole`: make a powerful role assumable.
- `iam:CreateAccessKey`, `iam:CreateLoginProfile`, `iam:UpdateLoginProfile`: take over other users.
- `iam:AddUserToGroup`: join a privileged group.
- `iam:PassRole` + `ec2:RunInstances` / `lambda:CreateFunction` + `lambda:InvokeFunction` / `ecs:RunTask` / `glue:CreateJob` / `cloudformation:CreateStack` / `sagemaker:CreateNotebookInstance` / `datapipeline`: run code as a more powerful role.
- `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration` (layers/env): run code with the function's role.
- `ssm:SendCommand` / `ssm:StartSession`, `ec2-instance-connect:SendSSHPublicKey`: execute on instances and use their instance-profile credentials.
- `sts:AssumeRole` on `*` or on a role with a trust that allows the account.
- `secretsmanager:GetSecretValue` / `ssm:GetParameter(s)` on `*`: read credentials stored there; `kms:Decrypt` on `*` unlocks encrypted data.
- `codebuild:StartBuild` / `codepipeline` roles, `s3:PutObject` into buckets feeding deployments: indirect code execution.
Mitigate: scope resources, add `iam:PassedToService`, `iam:PermissionsBoundary` conditions on identity creation, require tags, and use SCPs to deny the dangerous actions outside a break-glass role.

## Trust policy patterns
- **Third party (SaaS):** `sts:AssumeRole` + `sts:ExternalId` condition (unique per customer) to prevent confused deputy.
- **Within an organization:** `aws:PrincipalOrgID` instead of listing accounts; still name the principal where possible, not the whole account root.
- **GitHub Actions OIDC:** principal Federated `.../oidc-provider/token.actions.githubusercontent.com`, action `sts:AssumeRoleWithWebIdentity`, conditions `token.actions.githubusercontent.com:aud = sts.amazonaws.com` and `...:sub` pinned, for example `repo:ORG/REPO:ref:refs/heads/main` or `repo:ORG/REPO:environment:prod`. Wildcards such as `repo:ORG/*` allow every repository in the org (and any fork-created workflow where that is permitted by the sub pattern). Use separate roles for plan (read-only) and apply.
- **EKS IRSA / Pod Identity:** the trust condition pins namespace and service account (`...:sub = system:serviceaccount:NS:SA`); a missing or wildcard `sub` lets any pod assume the role.
- **Service principals in resource policies:** add `aws:SourceArn` and `aws:SourceAccount`.
- **Roles for humans:** require MFA (`aws:MultiFactorAuthPresent`), short sessions, SSO/Identity Center rather than IAM users.

## Resource policies worth checking
S3 (bucket policy, Block Public Access at account and bucket level, ACLs), KMS key policies (the key policy is the root of trust: if it does not allow IAM, IAM policies alone cannot grant access), SQS/SNS, Lambda resource policies, ECR repository policies, Secrets Manager, API Gateway resource policies, EFS file system policies, VPC endpoint policies.

## Useful read-only tools
```bash
aws accessanalyzer list-analyzers ; aws accessanalyzer list-findings --analyzer-arn ARN   # external and unused access
aws accessanalyzer validate-policy --policy-document file://p.json --policy-type IDENTITY_POLICY
aws iam generate-service-last-accessed-details --arn ROLE_ARN ; aws iam get-service-last-accessed-details --job-id ID
aws iam generate-credential-report ; aws iam get-credential-report                       # keys age, MFA, last used
aws iam simulate-principal-policy --policy-source-arn ARN --action-names s3:GetObject --resource-arns arn:aws:s3:::b/k
aws iam list-access-keys --user-name U ; aws iam get-access-key-last-used --access-key-id ID
aws sts decode-authorization-message --encoded-message MSG
```
`simulate-principal-policy` evaluates identity-based policies (and boundaries) but not every resource policy or SCP effect: treat it as a hint.
Access Analyzer "unused access" and CloudTrail-based policy generation turn real usage into a least-privilege policy. Allow at least 30-90 days of activity for the analysis to be meaningful, including rare jobs (month-end, DR).

## Account-level hygiene
Root has MFA and no access keys; no IAM users with console passwords where SSO exists; access keys rotated or removed; password policy; IAM Identity Center for humans; SCPs deny leaving the organization, disabling CloudTrail/GuardDuty, and creating IAM users/keys outside allowed paths; CloudTrail organization trail on; alerts on root login, policy changes and AssumeRole from new principals.
