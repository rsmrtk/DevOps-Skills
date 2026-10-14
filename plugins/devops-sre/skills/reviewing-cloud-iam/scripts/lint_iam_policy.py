#!/usr/bin/env python3
"""Static review of AWS IAM policy documents (identity, resource and trust policies).

Offline and read-only. Accepts JSON files that are a policy document, or AWS CLI output that wraps one
(get-policy-version, get-role, get-role-policy, get-bucket-policy, ...), or a JSON list of those.
Does not evaluate SCPs, permission boundaries, session policies or real account state.

Usage: lint_iam_policy.py FILE_OR_DIR [...] [--json]
Exit: 0 no high/critical, 1 at least one, 2 usage/parse problem.
"""
import json
import os
import re
import sys

SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
ESCALATION = {
    "iam:passrole": "can hand any role to a service it can start (PassRole + RunInstances/Lambda/CloudFormation)",
    "iam:createpolicyversion": "can rewrite a policy it is attached to into admin",
    "iam:setdefaultpolicyversion": "can activate an older, more permissive policy version",
    "iam:attachuserpolicy": "can attach AdministratorAccess to a user",
    "iam:attachrolepolicy": "can attach AdministratorAccess to a role",
    "iam:attachgrouppolicy": "can attach AdministratorAccess to a group",
    "iam:putuserpolicy": "can write an inline admin policy on a user",
    "iam:putrolepolicy": "can write an inline admin policy on a role",
    "iam:putgrouppolicy": "can write an inline admin policy on a group",
    "iam:updateassumerolepolicy": "can make any role assumable by itself",
    "iam:createaccesskey": "can mint keys for other users",
    "iam:createloginprofile": "can set a console password for other users",
    "iam:updateloginprofile": "can reset another user's console password",
    "iam:addusertogroup": "can join a privileged group",
    "lambda:updatefunctioncode": "can run code with the function's role",
    "lambda:createfunction": "with PassRole can run code as any passable role",
    "ec2:runinstances": "with PassRole can start an instance with any passable role",
    "glue:updatedevendpoint": "can run code with the endpoint's role",
    "cloudformation:createstack": "with PassRole can create resources as the passed role",
    "sts:assumerole": "can assume any role whose trust policy allows it",
    "ssm:sendcommand": "can run commands on instances (and use their roles)",
    "ssm:startsession": "can open a shell on instances (and use their roles)",
}
SENSITIVE_SERVICES = {"iam", "sts", "kms", "organizations", "secretsmanager", "ssm", "cloudformation"}
READONLY = re.compile(r"^(get|list|describe|batchget|lookup|view|head|search|select|scan|query)", re.I)
findings = []


def add(sev, fid, where, msg):
    findings.append({"severity": sev, "id": fid, "where": where, "message": msg})


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def find_policies(obj, path="$"):
    """Yield (path, policy_doc) for every dict that has a Statement."""
    if isinstance(obj, dict):
        if "Statement" in obj and ("Version" in obj or isinstance(obj["Statement"], (list, dict))):
            yield path, obj
            return
        for k, v in obj.items():
            yield from find_policies(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from find_policies(v, f"{path}[{i}]")
    elif isinstance(obj, str) and obj.lstrip().startswith("{"):
        try:
            yield from find_policies(json.loads(obj), path)
        except ValueError:
            pass


def principals(st):
    p = st.get("Principal")
    if p is None:
        return []
    if p == "*":
        return [("AWS", "*")]
    out = []
    if isinstance(p, dict):
        for k, v in p.items():
            for x in as_list(v):
                out.append((k, str(x)))
    return out


def cond_keys(st):
    keys = set()
    for op, body in (st.get("Condition") or {}).items():
        if isinstance(body, dict):
            for k in body:
                keys.add(k.lower())
    return keys


def check_statement(st, where):
    if not isinstance(st, dict):
        return
    effect = st.get("Effect")
    if effect != "Allow":
        return
    actions = [str(a) for a in as_list(st.get("Action"))]
    resources = [str(r) for r in as_list(st.get("Resource"))]
    sid = st.get("Sid", "")
    w = f"{where}{'/' + sid if sid else ''}"
    star_res = "*" in resources
    conds = cond_keys(st)

    if "NotAction" in st:
        add("high", "IAM004", w, "Allow + NotAction grants everything except the listed actions, including actions added to AWS later")
    if "NotResource" in st:
        add("medium", "IAM004", w, "Allow + NotResource grants the action on every resource except those listed")
    if "NotPrincipal" in st:
        add("high", "IAM004", w, "NotPrincipal with Allow is ambiguous and almost always wrong")

    if any(a == "*" for a in actions) and star_res:
        add("critical", "IAM001", w, "Action * on Resource *: full administrator")
    elif any(a == "*" for a in actions):
        add("high", "IAM001", w, f"Action * on {resources}: every action on those resources")

    for a in actions:
        la = a.lower()
        svc, _, act = la.partition(":")
        if act == "*" and svc in SENSITIVE_SERVICES:
            sev = "critical" if svc in ("iam", "organizations") else "high"
            add(sev, "IAM002", w, f"{a}: all actions of a sensitive service" + (" on Resource *" if star_res else ""))
        elif act == "*" and star_res and la != "*":
            add("medium", "IAM002", w, f"{a} on Resource *: whole service, all resources")
        for pat, why in ESCALATION.items():
            if la == pat or (la.endswith("*") and pat.startswith(la[:-1]) and la != "*"):
                if star_res or any(r.endswith(":*") or r == "arn:aws:iam::*:role/*" for r in resources):
                    if pat in ("iam:passrole",) and "iam:passedtoservice" in conds:
                        continue
                    add("high", "IAM003", w, f"{a} on a wildcard resource: privilege escalation, {why}")
                break

    if star_res and not any(a == "*" for a in actions):
        broad = [a for a in actions if not READONLY.match(a.split(":")[-1]) and a.split(":")[0].lower() not in ("logs", "xray", "cloudwatch")]
        if broad and not conds:
            add("medium", "IAM010", w, f"write/administrative actions on Resource * with no Condition: {broad[:4]}{'...' if len(broad) > 4 else ''} (some actions do not support resource-level permissions; verify)")
    if any(r in ("arn:aws:s3:::*", "arn:aws:s3:::*/*") for r in resources) and any(a.lower().startswith(("s3:*", "s3:put", "s3:delete")) for a in actions):
        add("medium", "IAM009", w, "S3 write/delete on every bucket")

    pr = principals(st)
    if any(v == "*" for _, v in pr):
        if not (conds - {"aws:sourcevpce", "aws:sourcevpc"}):
            add("critical", "IAM005", w, "Principal * without a Condition: anyone, including anonymous or any AWS account (verify intent, e.g. public website bucket)")
        else:
            add("medium", "IAM005", w, f"Principal * restricted only by condition keys {sorted(conds)}: verify they truly restrict")
    for kind, val in pr:
        if kind == "Federated" and "oidc" in val.lower() or kind == "Federated" and "token.actions.githubusercontent.com" in val:
            sub_keys = [k for k in conds if k.endswith(":sub")]
            if not sub_keys:
                add("critical", "IAM007", w, "OIDC federated trust without a `sub` condition: any identity from that provider can assume the role (for GitHub: any repo on GitHub)")
            else:
                for op, body in (st.get("Condition") or {}).items():
                    for k, v in (body or {}).items():
                        if k.lower().endswith(":sub"):
                            for x in as_list(v):
                                if str(x) in ("*",) or re.fullmatch(r"repo:[^/]*/?\*", str(x)) or str(x).endswith(":*") and str(x).count(":") <= 2:
                                    add("high", "IAM007", w, f"OIDC sub condition {x!r} is too broad: pin repo and ref/environment (e.g. repo:ORG/REPO:ref:refs/heads/main)")
            if not any(k.endswith(":aud") for k in conds):
                add("medium", "IAM007", w, "OIDC trust without an `aud` condition")
        if kind == "AWS" and re.fullmatch(r"(arn:aws:iam::)?\d{12}(:root)?", val) and "sts:assumerole" in [a.lower() for a in actions]:
            if "sts:externalid" not in conds and "aws:principalorgid" not in conds and "aws:sourceaccount" not in conds:
                add("medium", "IAM006", w, f"cross-account/account-root trust to {val} without ExternalId, PrincipalOrgID or other Condition: any principal in that account allowed to assume can use it (verify the account is yours)")
        if kind == "Service" and not ({"aws:sourcearn", "aws:sourceaccount", "aws:principalorgid"} & conds) and not actions == []:
            if any(x in val for x in ("sns", "s3", "events", "sqs", "cloudtrail", "config", "logs")):
                add("medium", "IAM008", w, f"service principal {val} without aws:SourceArn/SourceAccount: confused-deputy risk (another customer's resource can act through the service)")


def check_policy(doc, where):
    ver = doc.get("Version")
    if ver is None or ver == "2008-10-17":
        add("medium", "IAM011", where, f"Version {ver!r}: use 2012-10-17 (policy variables and newer features need it)")
    for i, st in enumerate(as_list(doc.get("Statement"))):
        check_statement(st, f"{where}.Statement[{i}]")


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        else:
            for root, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".json"):
                        yield os.path.join(root, f)


def main(argv):
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    n = 0
    for f in iter_files(paths):
        try:
            data = json.load(open(f))
        except Exception as e:
            print(f"cannot parse {f}: {e}", file=sys.stderr)
            return 2
        for path, doc in find_policies(data):
            n += 1
            check_policy(doc, f"{f}:{path}")
    findings.sort(key=lambda x: SEV[x["severity"]])
    if as_json:
        print(json.dumps(findings, indent=1))
    else:
        for x in findings:
            print(f"{x['severity'].upper():8} {x['id']:6} {x['where']}: {x['message']}")
        print(f"\n{len(findings)} finding(s) in {n} policy document(s). SCPs, permission boundaries, session policies and actual usage were not evaluated.")
    return 1 if any(x["severity"] in ("critical", "high") for x in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
