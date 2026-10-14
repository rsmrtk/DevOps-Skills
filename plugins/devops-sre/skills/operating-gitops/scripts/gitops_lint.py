#!/usr/bin/env python3
"""Read-only, offline linter for GitOps repos (Argo CD, Flux, Helm values, Kustomize, plain manifests).

Finds risky patterns a schema validator does not: plaintext Secrets, credentials in repo URLs, mutable
images/charts, `default` Argo project, commonLabels, Replace/Force sync options, prune settings.
Never prints secret values. Does not render Helm/Kustomize; run `kustomize build`/`helm template` for that.

Usage: gitops_lint.py PATH [PATH ...] [--json]
Exit code: 0 no high/critical, 1 at least one, 2 usage/parse problem. Requires PyYAML.
"""
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet", "Pod"}
SKIP_DIRS = {".git", "node_modules", ".terraform", "charts", "templates"}
findings = []


def add(sev, fid, where, msg):
    findings.append({"severity": sev, "id": fid, "where": where, "message": msg})


def pod_spec(doc):
    spec = doc.get("spec") or {}
    kind = doc.get("kind")
    if kind == "Pod":
        return spec
    if kind == "CronJob":
        return (((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}).get("spec") or {}
    return ((spec.get("template") or {}).get("spec")) or {}


def image_problem(img):
    if not isinstance(img, str) or "{{" in img or "$" in img:
        return None
    if "@sha256:" in img:
        return None
    last = img.rsplit("/", 1)[-1]
    if ":" not in last:
        return "no tag (defaults to latest)"
    tag = last.split(":", 1)[1]
    if tag == "latest":
        return "uses :latest"
    return None


def check_doc(doc, where):
    if not isinstance(doc, dict):
        return
    kind, api = doc.get("kind"), str(doc.get("apiVersion", ""))
    meta = doc.get("metadata") or {}
    name = meta.get("name", "?")
    w = f"{where}:{kind}/{name}"
    ann = meta.get("annotations") or {}

    if kind == "Secret":
        has_data = bool(doc.get("data") or doc.get("stringData"))
        if has_data and "sops" not in doc:
            add("critical", "GO001", w, "plaintext Secret in Git (values not shown; base64 is not encryption). Use SOPS, Sealed Secrets or External Secrets, and rotate it")
    if kind in WORKLOADS:
        ps = pod_spec(doc)
        for c in (ps.get("containers") or []) + (ps.get("initContainers") or []):
            p = image_problem(c.get("image"))
            if p:
                add("high", "GO003", w, f"container '{c.get('name')}' image {p}: a pod restart can change the version silently")
            sc = c.get("securityContext") or {}
            if sc.get("privileged"):
                add("high", "GO012", w, f"container '{c.get('name')}' is privileged")
            if not (c.get("resources") or {}).get("requests"):
                add("low", "GO013", w, f"container '{c.get('name')}' has no resource requests (scheduling and cost)")
        if ps.get("hostNetwork") or any("hostPath" in v for v in (ps.get("volumes") or []) if isinstance(v, dict)):
            add("medium", "GO012", w, "uses hostNetwork or hostPath")

    if api.startswith("argoproj.io") and kind in ("Application", "ApplicationSet"):
        spec = doc.get("spec") or {}
        tmpl = (spec.get("template") or {}).get("spec") if kind == "ApplicationSet" else spec
        tmpl = tmpl or {}
        if tmpl.get("project") in (None, "default"):
            add("medium", "GO004", w, "uses the `default` AppProject (no restrictions on repos, destinations, cluster-scoped kinds)")
        sources = list(tmpl.get("sources") or [])
        if tmpl.get("source"):
            sources.append(tmpl["source"])
        for s in sources:
            url = str(s.get("repoURL", ""))
            if re.match(r"https?://[^/@\s]+:[^/@\s]+@", url):
                add("critical", "GO005", w, "credentials embedded in repoURL (value not shown); use a repository credential Secret")
            rev = s.get("targetRevision")
            if s.get("chart"):
                if rev in (None, "", "*", "HEAD", "latest") or (isinstance(rev, str) and re.search(r"[\^~*xX><]", rev)):
                    add("high", "GO006", w, f"Helm chart '{s.get('chart')}' targetRevision {rev!r} is not an exact version")
            elif rev in ("HEAD",) and "third" in str(url).lower():
                add("low", "GO006", w, "targetRevision HEAD on a third-party repo")
        pol = tmpl.get("syncPolicy") or {}
        auto = pol.get("automated")
        opts = pol.get("syncOptions") or []
        if auto and auto.get("prune"):
            add("low", "GO007", w, "automated prune: removing a manifest deletes the live resource (protect stateful objects with Prune=false)")
        for o in opts:
            if str(o).startswith(("Replace=true", "Force=true")):
                add("medium", "GO008", w, f"sync option {o}: delete-and-recreate semantics, can cause downtime")
        if kind == "Application" and "resources-finalizer.argocd.argoproj.io" in (meta.get("finalizers") or []):
            add("info", "GO009", w, "resources finalizer: deleting this Application deletes everything it manages")
        if kind == "ApplicationSet" and not (spec.get("syncPolicy") or {}).get("preserveResourcesOnDeletion"):
            add("low", "GO009", w, "ApplicationSet without preserveResourcesOnDeletion: removing a generator element deletes that app's resources")

    if "toolkit.fluxcd.io" in api:
        spec = doc.get("spec") or {}
        if kind == "HelmRelease":
            ver = ((spec.get("chart") or {}).get("spec") or {}).get("version")
            if ver in (None, "", "*") or (isinstance(ver, str) and re.search(r"[\^~*xX><]", ver)):
                add("high", "GO006", w, f"HelmRelease chart version {ver!r} is not exact: upstream releases reach the cluster unreviewed")
            if not spec.get("upgrade", {}).get("remediation") and not spec.get("install", {}).get("remediation"):
                add("low", "GO010", w, "no install/upgrade remediation configured (retries, rollback)")
        if kind == "Kustomization":
            if spec.get("prune") is True and not spec.get("serviceAccountName"):
                add("low", "GO010", w, "prune enabled with no serviceAccountName: runs with controller privileges (fine for platform, risky for tenants)")
            if spec.get("force") is True:
                add("medium", "GO008", w, "force: true recreates objects that fail to patch (can cause downtime)")
            if spec.get("suspend") is True:
                add("medium", "GO011", w, "suspended: Flux is not reconciling this, drift will persist")
        if kind == "GitRepository":
            url = str((spec.get("url")) or "")
            if re.match(r"https?://[^/@\s]+:[^/@\s]+@", url):
                add("critical", "GO005", w, "credentials embedded in url (value not shown); use secretRef")

    if kind == "Kustomization" and api.startswith("kustomize.config.k8s.io"):
        if doc.get("commonLabels"):
            add("medium", "GO014", w, "commonLabels rewrites immutable selectors of Deployments/StatefulSets; use `labels` with includeSelectors: false")
        for r in doc.get("resources") or []:
            if isinstance(r, str) and re.match(r"(https?://|git@|github\.com/)", r) and "ref=" not in r:
                add("medium", "GO006", w, f"remote base '{r}' without ?ref=<tag or commit>: follows the default branch")
        for im in doc.get("images") or []:
            if im.get("newTag") in ("latest",):
                add("high", "GO003", w, f"images override {im.get('name')} newTag latest")


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        else:
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    if f.endswith((".yaml", ".yml")) and f not in ("Chart.yaml",):
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
            txt = open(f).read()
        except Exception:
            continue
        if "{{" in txt:
            continue  # Helm template source, not renderable YAML
        try:
            docs = list(yaml.safe_load_all(txt))
        except Exception as e:
            add("low", "GO000", f, f"unparseable YAML ({str(e).splitlines()[0][:60]})")
            continue
        n += 1
        for d in docs:
            check_doc(d, f)
    findings.sort(key=lambda x: SEV[x["severity"]])
    if as_json:
        print(json.dumps(findings, indent=1))
    else:
        for x in findings:
            print(f"{x['severity'].upper():8} {x['id']:6} {x['where']}: {x['message']}")
        print(f"\n{len(findings)} finding(s) in {n} file(s). Helm/Kustomize output was not rendered; schema validation (kubeconform) was not run.")
    return 1 if any(x["severity"] in ("critical", "high") for x in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
