# GCP and Azure access reference

Read-only commands are templates; check `--help`. The same principles apply: scope narrowly, avoid long-lived credentials, find escalation chains, use real usage data.

## GCP IAM
- **Model:** a member (user, group, service account, workload identity) gets a **role** on a **resource** in the hierarchy (organization → folder → project → resource). Policies are inherited downwards: a role at the folder applies to every project below. Deny policies and organization policies restrict.
- **Avoid basic roles** (`roles/owner`, `roles/editor`, `roles/viewer`): very broad. Use predefined or custom roles. `roles/editor` can do almost everything in a project except IAM.
- **Public access:** bindings to `allUsers` or `allAuthenticatedUsers` make resources public to the internet or to any Google account. Find them.
- **Escalation paths:** `iam.serviceAccounts.actAs` (role `roles/iam.serviceAccountUser`) lets a principal run workloads as that service account; `iam.serviceAccounts.getAccessToken` / `roles/iam.serviceAccountTokenCreator` mint tokens for it; `iam.serviceAccountKeys.create` creates a long-lived key; `resourcemanager.projects.setIamPolicy` / `setIamPolicy` on any level grants anything; `deploymentmanager`, `cloudbuild` (default build service account is powerful), `compute.instances.setMetadata` / OS Login (SSH to VMs with attached SAs), `cloudfunctions.functions.create` + `actAs`.
- **Service account keys:** prefer Workload Identity Federation (for GitHub Actions: pool + provider with an attribute condition pinning the repository, e.g. `assertion.repository == 'ORG/REPO'`) or attached service accounts over downloaded JSON keys. Enforce `iam.disableServiceAccountKeyCreation` via organization policy.
- **Default service accounts** (Compute Engine default, App Engine default) often hold Editor: replace with dedicated least-privilege accounts and disable automatic Editor grants (organization policy).
```bash
gcloud projects get-iam-policy PROJECT --format=json
gcloud asset search-all-iam-policies --scope=organizations/ORG_ID --query='policy:allUsers OR policy:allAuthenticatedUsers'
gcloud iam service-accounts list --project PROJECT
gcloud iam service-accounts keys list --iam-account SA --managed-by=user     # user-managed keys: age and need
gcloud recommender recommendations list --recommender=google.iam.policy.Recommender --project PROJECT --location=global
gcloud policy-troubleshoot iam RESOURCE --principal-email=EMAIL --permission=PERMISSION
```
The IAM recommender (role recommendations from observed usage) is the GCP equivalent of Access Advisor: use it to shrink roles.

## Azure RBAC and Entra ID
- **Model:** a principal gets a **role definition** at a **scope** (management group → subscription → resource group → resource); inherited downward. Entra ID directory roles (Global Administrator, Privileged Role Administrator, Application Administrator...) are separate from Azure RBAC.
- **Owner** and **User Access Administrator** at subscription or management-group scope can grant anything; **Contributor** can change resources but not role assignments. Avoid assigning at subscription scope when a resource group suffices. `Microsoft.Authorization/*/write` allows self-escalation.
- **Escalation paths:** Global Administrator can elevate to manage all subscriptions; Application Administrator or owners of an app registration can add credentials to a privileged service principal; Contributor on a VM or automation account can run code under its managed identity; Key Vault access policies or `Key Vault Secrets User` expose secrets; `Microsoft.Compute/virtualMachines/runCommand/action`.
- **Identities for workloads:** managed identities (system- or user-assigned) instead of app registration secrets; secrets and certificates on app registrations expire and are leaked easily: inventory them. For GitHub Actions use workload identity federation with a federated credential pinned to repo and branch/environment.
- **Humans:** Privileged Identity Management (PIM) for just-in-time, approval-based elevation; Conditional Access with MFA; no standing Global Admin; break-glass accounts monitored.
```bash
az role assignment list --all --include-inherited --query "[?roleDefinitionName=='Owner' || roleDefinitionName=='User Access Administrator'].{p:principalName,r:roleDefinitionName,s:scope}" -o table
az role assignment list --scope /subscriptions/SUB --query "[?principalType=='ServicePrincipal']" -o table
az ad app list --all --query "[].{n:displayName,id:appId}"            # then check credentials per app
az keyvault list ; az keyvault show --name KV --query properties.enableRbacAuthorization
az graph query -q "authorizationresources | where type =~ 'microsoft.authorization/roleassignments' | extend rd=tostring(properties.roleDefinitionId) | summarize count() by rd"
```
Use Azure Advisor/Defender for Cloud recommendations and the access reviews feature to find stale assignments.

## Cross-cloud checks
Long-lived keys anywhere (AWS access keys, GCP SA keys, Azure app secrets); CI/CD identities with admin rights; wildcard trust on OIDC; humans with standing admin; no review cadence for access; no alert on privilege-granting events (policy changes, role assignments, new keys).
