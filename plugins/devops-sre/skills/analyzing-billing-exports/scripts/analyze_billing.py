#!/usr/bin/env python3
"""Analyze a cloud billing export (AWS CUR / Data Exports CSV, GCP BigQuery billing export CSV/JSONL,
Azure Cost Management export CSV) and print facts a human or an LLM can trust.

Offline, read-only, standard library only, streams the file (handles hundreds of MB).
It reports: what the cost columns mean, month totals with day coverage (partial months flagged),
line-type breakdown (usage vs credits/tax/negations), top services and month-over-month drivers
(complete months only), daily anomalies, idle-resource suspects, tag coverage with case-normalized values.

Usage:
  analyze_billing.py FILE [--tag KEY] [--top N] [--json] [--month YYYY-MM]
Exit: 0 ok, 2 unreadable or unrecognized format.
"""
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime

csv.field_size_limit(sys.maxsize)


def norm(h):
    return re.sub(r"[^a-z0-9]", "", h.lower())


# canonical field -> candidate normalized header names (first match wins)
CANDIDATES = {
    "date": ["lineitemusagestartdate", "usagestartdate", "usagestarttime", "usagedate", "date", "chargeperiodstart", "billingperiodstartdate", "usagestart"],
    "cost": ["lineitemunblendedcost", "unblendedcost", "costinbillingcurrency", "cost", "pretaxcost", "costusd", "billedcost", "effectivecost"],
    "net_cost": ["lineitemnetunblendedcost", "netunblendedcost"],
    "credits": ["credits"],
    "line_type": ["lineitemlineitemtype", "lineitemtype", "chargetype", "pricingmodel", "chargecategory"],
    "service": ["lineitemproductcode", "productcode", "productproductname", "servicedescription", "servicename", "metercategory", "consumedservice", "producttype"],
    "usage_type": ["lineitemusagetype", "usagetype", "skudescription", "metername", "metersubcategory", "skuid"],
    "resource": ["lineitemresourceid", "resourceid", "resourcename", "instanceid", "resourcegroupname", "resourcegroup"],
    "account": ["lineitemusageaccountid", "usageaccountid", "projectid", "subscriptionid", "subscriptionname", "billingaccountid", "payeraccountid"],
    "region": ["productregion", "productregioncode", "locationregion", "resourcelocation", "region"],
    "usage_amount": ["lineitemusageamount", "usageamount", "usageamountinpricingunits", "quantity", "consumedquantity", "usagequantity"],
    "currency": ["lineitemcurrencycode", "currencycode", "currency", "billingcurrency", "billingcurrencycode"],
    "tags": ["tags", "labels", "resourcetags", "labelsjson"],
}
DATE_FORMATS = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S.%f UTC", "%Y-%m-%d %H:%M:%S UTC"]


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        except ValueError:
            pass
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def to_float(x):
    if x is None or x == "":
        return 0.0
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return 0.0


def detect_columns(header):
    nh = {norm(h): h for h in header}
    cols = {}
    for field, cands in CANDIDATES.items():
        for c in cands:
            if c in nh:
                cols[field] = nh[c]
                break
    # tag columns exposed as one column per tag (AWS: resourceTags/user:Environment)
    tagcols = {h: re.sub(r"^.*?(user:|resourcetags[/_.]?)", "", h, flags=re.I) for h in header if re.search(r"resourcetags|resource_tags|^tags[/_.]|^labels[/_.]", h, re.I)}
    return cols, tagcols


def iter_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        head = f.read(2048)
        f.seek(0)
        if head.lstrip().startswith("{"):
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
            return
        for r in csv.DictReader(f):
            yield r


def gcp_credit_sum(v):
    if not v:
        return 0.0
    try:
        arr = json.loads(v) if isinstance(v, str) else v
        return sum(to_float(c.get("amount")) for c in arr if isinstance(c, dict))
    except Exception:
        return 0.0


def flat(r, key):
    """Support nested JSON export objects like service.description."""
    return r.get(key)


def main(argv):
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    opts = {}
    for i, a in enumerate(argv):
        if a in ("--tag", "--top", "--month") and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            if argv[i + 1] in args:
                args.remove(argv[i + 1])
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    top = int(opts.get("top", 8))
    try:
        it = iter_rows(path)
        first = next(it)
    except StopIteration:
        print("empty file", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"cannot read {path}: {e}", file=sys.stderr)
        return 2
    # flatten JSON objects into dotted keys so one code path handles CSV and JSONL
    def flatten(r, p=""):
        out = {}
        for k, v in r.items():
            kk = f"{p}{k}"
            if isinstance(v, dict) and k not in ("labels",):
                out.update(flatten(v, kk + "."))
            else:
                out[kk] = v
        return out
    first = flatten(first)
    cols, tagcols = detect_columns(list(first.keys()))
    if "date" not in cols or "cost" not in cols:
        print(f"unrecognized format: need a date and a cost column. Columns seen: {list(first.keys())[:25]}", file=sys.stderr)
        return 2
    fmt = ("aws" if "line_type" in cols and "lineitem" in norm(cols["cost"]) else
           "gcp" if "credits" in cols else
           "azure" if "costinbillingcurrency" in norm(cols["cost"]) or "pretaxcost" in norm(cols["cost"]) else "generic")
    use_cost_col = cols["cost"]
    notes = []
    if "net_cost" in cols:
        notes.append(f"file has a net cost column ({cols['net_cost']}); 'cost' below uses {use_cost_col} (before private-pricing/EDP discounts). Compare both if discounts matter.")
    if fmt == "gcp":
        notes.append("GCP: 'cost' is before credits; credits are listed separately. Net = cost + credits (credits are negative).")
    if fmt == "aws":
        notes.append("AWS: all line types are summed (Usage, SavingsPlanCoveredUsage + SavingsPlanNegation cancel, SavingsPlanRecurringFee, Credit, Tax, Fee, Refund). Filtering to Usage only gives a wrong total.")
    if fmt == "azure":
        notes.append("Azure: reservation purchases appear as charges in the period they are billed; amortized views differ.")

    month_cost = defaultdict(float)
    month_days = defaultdict(set)
    month_rows = defaultdict(int)
    by_type = defaultdict(lambda: defaultdict(float))        # month -> line type -> cost
    svc_month = defaultdict(lambda: defaultdict(float))       # service -> month -> cost
    key_month = defaultdict(lambda: defaultdict(float))       # (service|usage_type) -> month -> cost
    day_svc = defaultdict(lambda: defaultdict(float))         # service|usage_type -> day -> cost
    day_total = defaultdict(float)
    res_cost = defaultdict(float)
    res_info = {}
    acct_month = defaultdict(lambda: defaultdict(float))
    credits_total = defaultdict(float)
    idle = defaultdict(lambda: [0.0, 0.0, set()])             # resource -> [cost, usage, months]
    tagkey = opts.get("tag")
    tag_cost = defaultdict(lambda: defaultdict(float))        # month -> normalized tag value -> cost
    tag_raw = defaultdict(set)
    tag_col = None
    if tagkey:
        for h, t in tagcols.items():
            if t.lower().replace("user:", "") == tagkey.lower():
                tag_col = h
    elif tagcols:
        pref = [h for h, t in tagcols.items() if t.lower().replace("user:", "") in ("environment", "env", "team", "owner", "project", "costcenter")]
        tag_col = pref[0] if pref else None
    only_month = opts.get("month")
    currencies = set()
    rows = 0
    unparsed_dates = 0

    def rows_iter():
        yield first
        for r in it:
            yield flatten(r)

    for r in rows_iter():
        rows += 1
        d = parse_date(str(r.get(cols["date"], "")))
        if d is None:
            unparsed_dates += 1
            continue
        m = f"{d.year}-{d.month:02d}"
        if only_month and m != only_month:
            continue
        c = to_float(r.get(use_cost_col))
        if fmt == "gcp":
            cr = gcp_credit_sum(r.get(cols["credits"]))
            credits_total[m] += cr
        lt = (r.get(cols.get("line_type", ""), "") or "Usage") if "line_type" in cols else "n/a"
        svc = (r.get(cols.get("service", ""), "") or "unknown") if "service" in cols else "unknown"
        ut = (r.get(cols.get("usage_type", ""), "") or "") if "usage_type" in cols else ""
        res = (r.get(cols.get("resource", ""), "") or "") if "resource" in cols else ""
        acct = (r.get(cols.get("account", ""), "") or "") if "account" in cols else ""
        month_cost[m] += c
        month_days[m].add(d)
        month_rows[m] += 1
        by_type[m][lt] += c
        svc_month[svc][m] += c
        key_month[f"{svc} | {ut}"][m] += c
        day_svc[f"{svc} | {ut}"][d] += c
        day_total[d] += c
        acct_month[acct][m] += c
        if res:
            res_cost[res] += c
            res_info.setdefault(res, (svc, ut, acct))
            amt = to_float(r.get(cols.get("usage_amount", ""))) if "usage_amount" in cols else 0.0
            ent = idle[res]
            ent[0] += c
            ent[1] += amt
            ent[2].add(m)
        if "currency" in cols:
            currencies.add(r.get(cols["currency"], ""))
        if tag_col:
            raw = (r.get(tag_col, "") or "").strip()
            tag_raw[raw.lower()].add(raw)
            tag_cost[m][raw.lower()] += c

    months = sorted(month_cost)
    if not months:
        print("no rows in the selected period", file=sys.stderr)
        return 2
    # month coverage
    cov = {}
    for m in months:
        y, mo = map(int, m.split("-"))
        ndays = (date(y + (mo == 12), mo % 12 + 1, 1) - date(y, mo, 1)).days
        seen = sorted(month_days[m])
        full = len(seen) == ndays and seen[0].day == 1
        cov[m] = {"days_present": len(seen), "days_in_month": ndays, "first": seen[0].isoformat(), "last": seen[-1].isoformat(), "complete": full}
    complete = [m for m in months if cov[m]["complete"]]

    out = {"file": path, "format": fmt, "rows": rows, "unparsed_date_rows": unparsed_dates, "cost_column": use_cost_col,
           "currency": sorted(c for c in currencies if c) or ["unknown"], "notes": notes, "months": {}}
    for m in months:
        mc = round(month_cost[m], 2)
        entry = {"total": mc, **cov[m], "rows": month_rows[m], "by_line_type": {k: round(v, 2) for k, v in sorted(by_type[m].items(), key=lambda kv: -abs(kv[1]))}}
        if fmt == "gcp":
            entry["credits"] = round(credits_total[m], 2)
            entry["net_after_credits"] = round(mc + credits_total[m], 2)
        if not cov[m]["complete"]:
            entry["per_day_avg"] = round(month_cost[m] / cov[m]["days_present"], 2)
            entry["warning"] = f"PARTIAL month ({cov[m]['days_present']}/{cov[m]['days_in_month']} days, {cov[m]['first']}..{cov[m]['last']}): do not compare its total with full months; compare per-day averages"
            entry["linear_projection"] = round(entry["per_day_avg"] * cov[m]["days_in_month"], 2)
        out["months"][m] = entry
    # service ranking for latest complete month (or last month)
    ref = complete[-1] if complete else months[-1]
    out["reference_month"] = ref
    out["top_services_reference_month"] = [{"service": s, "cost": round(v.get(ref, 0.0), 2)} for s, v in sorted(svc_month.items(), key=lambda kv: -kv[1].get(ref, 0.0))[:top]]
    out["top_accounts_reference_month"] = [{"account": a, "cost": round(v.get(ref, 0.0), 2)} for a, v in sorted(acct_month.items(), key=lambda kv: -kv[1].get(ref, 0.0))[:top]]
    # MoM drivers between the last two complete months
    if len(complete) >= 2:
        a, b = complete[-2], complete[-1]
        deltas = []
        for k, v in key_month.items():
            dlt = v.get(b, 0.0) - v.get(a, 0.0)
            if abs(dlt) > 0.0:
                deltas.append((k, v.get(a, 0.0), v.get(b, 0.0), dlt))
        deltas.sort(key=lambda x: -abs(x[3]))
        out["mom"] = {"from": a, "to": b, "total_delta": round(month_cost[b] - month_cost[a], 2),
                      "drivers": [{"service|usage_type": k, a: round(x, 2), b: round(y, 2), "delta": round(dl, 2), "share_of_total_delta_pct": round(100 * dl / (month_cost[b] - month_cost[a]), 1) if month_cost[b] != month_cost[a] else None,
                                   "new_in_period": x == 0.0} for k, x, y, dl in deltas[:top]]}
        out["mom"]["note"] = "Drivers are grouped by service | usage type. A usage type with zero cost in the earlier month is a NEW cost line. Sum of all deltas equals total_delta."
    elif len(months) >= 2:
        out["mom"] = {"note": "Fewer than two complete months: month-over-month comparison skipped to avoid comparing a partial month with a full one."}
    # daily anomalies per service|usage_type against a trailing 14-day median; consecutive flagged days form one event
    events = []
    file_start = min(day_total) if day_total else None
    new_lines = []
    for key, days in day_svc.items():
        ds = sorted(days)
        if file_start and (ds[0] - file_start).days > 3 and sum(days.values()) >= 50:
            new_lines.append({"service|usage_type": key, "kind": "new cost line (one-off)" if len(ds) <= 2 else "new cost line (recurring)", "start": ds[0].isoformat(), "end": ds[-1].isoformat(), "days": len(ds), "cost_in_event_days": round(sum(days.values()), 2), "baseline_per_day": 0.0, "excess_over_baseline": round(sum(days.values()), 2)})
            continue
        flagged = []
        for idx, d in enumerate(ds):
            prior = [days[x] for x in ds[max(0, idx - 14):idx]]
            if len(prior) < 3:
                continue          # not enough history to define a baseline
            base = statistics.median(prior)
            v = days[d]
            if v - base > max(50.0, 0.5 * abs(base)):
                flagged.append((d, v, base))
        cur = None
        for f in flagged:
            if cur is not None and (f[0] - cur[-1][0]).days == 1:
                cur.append(f)
            else:
                cur = [f]
                events.append((key, cur))
    out_events = []
    for key, cur in events:
        start, end = cur[0][0], cur[-1][0]
        excess = sum(v - b for _, v, b in cur)
        kind = "one-off spike" if len(cur) <= 2 else "sustained step change"
        out_events.append({"service|usage_type": key, "kind": kind, "start": start.isoformat(), "end": end.isoformat(), "days": len(cur),
                           "cost_in_event_days": round(sum(v for _, v, _ in cur), 2), "baseline_per_day": round(cur[0][2], 2), "excess_over_baseline": round(excess, 2)})
    out_events += new_lines
    out_events.sort(key=lambda x: -x["excess_over_baseline"])
    out["daily_anomalies"] = out_events[:top]
    out["daily_anomalies_note"] = "Day totals per service|usage_type compared with the trailing 14-day median; consecutive days are merged into one event. A step change that began before the file starts is not visible."
    # top resources
    out["top_resources"] = [{"resource": r, "cost": round(c, 2), "service": res_info[r][0], "usage_type": res_info[r][1]} for r, c in sorted(res_cost.items(), key=lambda kv: -kv[1])[:top]]
    # idle suspects
    sus = []
    for r, (c, u, ms) in idle.items():
        svc, ut, acct = res_info[r]
        if re.search(r"idle|unattached|unused", ut, re.I) and c > 0:
            sus.append({"resource": r, "cost": round(c, 2), "usage_type": ut, "reason": "usage type itself says idle/unattached/unused", "account": acct})
    sus.sort(key=lambda x: -x["cost"])
    out["idle_suspects"] = {"count": len(sus), "total_cost_in_file": round(sum(s["cost"] for s in sus), 2), "by_month": None, "items": sus[:top * 3]}
    if sus:
        per_m = defaultdict(float)
        sset = {s["resource"] for s in sus}
        # per-month cost of the suspects requires a second pass over stored aggregates; approximate via idle monthly sets is not exact, so say so
        out["idle_suspects"]["by_month"] = "not computed (billing shows cost, not attachment state): confirm each resource in the cloud console/API before deleting"
    # tags
    if tag_col:
        tagname = tagcols[tag_col]
        tout = {"tag": tagname, "months": {}}
        for m in months:
            tot = month_cost[m]
            vals = {}
            for k, c in tag_cost[m].items():
                label = "(untagged)" if k == "" else k
                vals[label] = round(c, 2)
            variants = {k: sorted(v) for k, v in tag_raw.items() if len(v) > 1}
            tout["months"][m] = {"values_case_folded": dict(sorted(vals.items(), key=lambda kv: -kv[1])), "untagged": round(tag_cost[m].get("", 0.0), 2),
                                 "untagged_pct_of_total": round(100 * tag_cost[m].get("", 0.0) / tot, 1) if tot else None}
        tout["case_variants"] = {k: v for k, v in variants.items()} if tag_col else {}
        tout["note"] = "Values are case-folded only. Also look for synonyms (prod/production, dev/development) and merge them manually before reporting per-environment totals."
        out["tags"] = tout
    out["limits"] = ["Reads only this file: no attachment state, no utilization, no discounts outside the columns present.",
                     "Granularity limits what can be seen (daily/hourly rows). Billing arrives after the fact; recent days can still change."]
    if as_json:
        print(json.dumps(out, indent=1, default=str))
        return 0
    # human text
    print(f"FILE {path}  format={out['format']}  rows={rows}  cost column={use_cost_col}  currency={','.join(out['currency'])}")
    for n in notes:
        print("NOTE:", n)
    print("\nMONTHS")
    for m, e in out["months"].items():
        flag = "" if e["complete"] else "  ** PARTIAL **"
        print(f"  {m}: total {e['total']:>12,.2f}  days {e['days_present']}/{e['days_in_month']} ({e['first']}..{e['last']}){flag}")
        types = ", ".join(f"{k}={v:,.2f}" for k, v in list(e["by_line_type"].items())[:8])
        print(f"      line types: {types}")
        if not e["complete"]:
            print(f"      per-day avg {e['per_day_avg']:,.2f}; linear projection for full month {e['linear_projection']:,.2f} (an estimate, not a forecast)")
        if "credits" in e:
            print(f"      credits {e['credits']:,.2f}; net after credits {e['net_after_credits']:,.2f}")
    print(f"\nTOP SERVICES in {ref}")
    for s in out["top_services_reference_month"]:
        print(f"  {s['cost']:>12,.2f}  {s['service']}")
    print(f"\nTOP ACCOUNTS in {ref}")
    for s in out["top_accounts_reference_month"]:
        print(f"  {s['cost']:>12,.2f}  {s['account']}")
    if "mom" in out and "drivers" in out["mom"]:
        mm = out["mom"]
        print(f"\nMONTH OVER MONTH {mm['from']} -> {mm['to']}: total delta {mm['total_delta']:,.2f}")
        for dr in mm["drivers"]:
            new = "  [NEW]" if dr["new_in_period"] else ""
            print(f"  {dr['delta']:>+12,.2f} ({dr['share_of_total_delta_pct']}% of delta)  {dr['service|usage_type']}{new}")
    elif "mom" in out:
        print("\nMONTH OVER MONTH:", out["mom"]["note"])
    print("\nDAILY ANOMALIES (vs trailing 14-day median)")
    for a in out["daily_anomalies"] or []:
        print(f"  {a['kind']}: {a['service|usage_type']} {a['start']}..{a['end']} ({a['days']} d), excess over baseline {a['excess_over_baseline']:,.2f} (baseline {a['baseline_per_day']:,.2f}/day)")
    if not out["daily_anomalies"]:
        print("  none detected")
    print("\nTOP RESOURCES (whole file)")
    for r in out["top_resources"]:
        print(f"  {r['cost']:>12,.2f}  {r['resource']}  ({r['service']} | {r['usage_type']})")
    iss = out["idle_suspects"]
    print(f"\nIDLE SUSPECTS: {iss['count']} resources, {iss['total_cost_in_file']:,.2f} over the whole file (billing text says idle/unattached/unused; confirm in the cloud API)")
    for s in iss["items"][:top]:
        print(f"  {s['cost']:>10,.2f}  {s['resource']}  {s['usage_type']}")
    if "tags" in out:
        t = out["tags"]
        print(f"\nTAG {t['tag']}")
        for m, e in t["months"].items():
            print(f"  {m}: untagged {e['untagged']:,.2f} ({e['untagged_pct_of_total']}% of total); values {e['values_case_folded']}")
        print("  " + t["note"])
    print("\nLIMITS:", " ".join(out["limits"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
