#!/usr/bin/env python3
"""Generate a synthetic AWS CUR-like CSV (Aug, Sep full; Oct 1-12 only) with planted facts + truth.json."""
import csv, json, random, datetime as dt
random.seed(7)
OUT="cur.csv"  # run: python3 gen_fixture.py (writes cur.csv and truth.json next to it)
hdr=["identity/LineItemId","lineItem/UsageAccountId","lineItem/UsageStartDate","lineItem/LineItemType","lineItem/ProductCode",
     "lineItem/UsageType","lineItem/ResourceId","lineItem/UsageAmount","lineItem/UnblendedCost","lineItem/CurrencyCode",
     "product/region","resourceTags/user:Environment"]
ACC={"111111111111":"prod","222222222222":"dev"}
start=dt.date(2026,8,1); last=dt.date(2026,10,12)
days=(last-start).days+1
rows=[]; truth={"planted":{}}
def row(d,acct,ltype,prod,ut,rid,amt,cost,reg="eu-west-1",env=None):
    rows.append([f"L{len(rows)}",acct,d.isoformat()+"T00:00:00Z",ltype,prod,ut,rid,f"{amt:.4f}",f"{cost:.6f}","USD",reg,env if env is not None else ""])
def jitter(x,p=0.06): return x*(1+random.uniform(-p,p))
envs_prod=["prod","prod","prod","Prod","production","prod",""]   # messy tag values + untagged
envs_dev=["dev","dev","Dev","development","","dev"]
# baseline fleet
ec2=[(f"i-{a}{i:04x}",a) for a in ACC for i in range(40)]
for n in range(days):
    d=start+dt.timedelta(n)
    for rid,a in ec2:
        env=random.choice(envs_prod if a=="111111111111" else envs_dev)
        rate=0.096 if a=="111111111111" else 0.048
        for h in range(24):
            rows.append([f"L{len(rows)}",a,d.isoformat()+f"T{h:02d}:00:00Z","Usage","AmazonEC2","BoxUsage:m5.large",rid,"1.0000",f"{jitter(rate):.6f}","USD","eu-west-1",env])
    for k in range(30):   # S3 buckets
        a="111111111111" if k<20 else "222222222222"
        row(d,a,"Usage","AmazonS3","TimedStorage-ByteHrs",f"bucket-{k}",1000,jitter(1.8+k*0.07),env=random.choice(envs_prod if a=="111111111111" else envs_dev))
    for k in range(12):   # RDS
        a="111111111111" if k<8 else "222222222222"
        row(d,a,"Usage","AmazonRDS","InstanceUsage:db.r5.large",f"db-{k}",24,jitter(24*0.29 if a=="111111111111" else 24*0.14),env=random.choice(envs_prod[:3] if a=="111111111111" else envs_dev))
    # NAT baseline
    for a in ACC:
        row(d,a,"Usage","AmazonEC2","NatGateway-Hours",f"nat-{a[:3]}",24,24*0.048,env="prod" if a=="111111111111" else "dev")
        row(d,a,"Usage","AmazonEC2","NatGateway-Bytes",f"nat-{a[:3]}",200,200*0.048*jitter(1,0.1)*0.5,env="prod" if a=="111111111111" else "dev")
    # savings plan: covered usage + negation + recurring fee (net zero except fee)
    cov=jitter(310); 
    row(d,"111111111111","SavingsPlanCoveredUsage","AmazonEC2","BoxUsage:m5.large","sp-covered",0,cov,env="prod")
    row(d,"111111111111","SavingsPlanNegation","AmazonEC2","BoxUsage:m5.large","sp-covered",0,-cov,env="prod")
    row(d,"111111111111","SavingsPlanRecurringFee","AmazonEC2","SavingsPlanRecurringFee","sp-1",0,190.0,env="prod")
    # idle EIPs: 14 idle addresses all period
    for k in range(14):
        row(d,"222222222222","Usage","AmazonVPC","PublicIPv4:IdleAddress",f"eipalloc-idle{k:02d}",24,24*0.005,reg="eu-west-1",env="dev")
# planted 1: NAT bytes surge in prod from Sep 10 (adds extra)
extra_nat=0.0
for n in range(days):
    d=start+dt.timedelta(n)
    if d>=dt.date(2026,9,10):
        c=jitter(260,0.05); extra_nat+= c if d<=dt.date(2026,9,30) else 0
        row(d,"111111111111","Usage","AmazonEC2","NatGateway-Bytes","nat-111",9000,c,env="prod")
truth["planted"]["nat_surge_sep_extra"]=round(extra_nat,2)
# planted 2: new service from Sep 15: OpenSearch
os_sep=0.0
for n in range(days):
    d=start+dt.timedelta(n)
    if d>=dt.date(2026,9,15):
        c=jitter(180,0.03); 
        if d<=dt.date(2026,9,30): os_sep+=c
        row(d,"111111111111","Usage","AmazonES","ESInstance:r6g.xlarge.search","os-domain-1",24,c,env="prod")
truth["planted"]["opensearch_sep"]=round(os_sep,2)
# planted 3: one-day data transfer spike Sep 17
row(dt.date(2026,9,17),"111111111111","Usage","AmazonEC2","DataTransfer-Out-Bytes","i-111100005",42000,5200.0,env="prod")
truth["planted"]["spike_date"]="2026-09-17"; truth["planted"]["spike_amount"]=5200.0
# credits and tax
row(dt.date(2026,9,5),"111111111111","Credit","AWSSupportBusiness","Credit","credit-1",0,-3000.0,env="prod")
row(dt.date(2026,9,30),"111111111111","Tax","Tax","Tax","tax",0,1240.55,env="prod")
random.shuffle(rows)
with open(OUT,"w",newline="") as f:
    w=csv.writer(f); w.writerow(hdr); w.writerows(rows)
def tot(pred):
    s=0.0
    for r in rows:
        if pred(r): s+=float(r[8])
    return round(s,2)
sep=lambda r:r[2].startswith("2026-09"); aug=lambda r:r[2].startswith("2026-08"); octo=lambda r:r[2].startswith("2026-10")
truth["rows"]=len(rows)
truth["sep_total_all_lines"]=tot(sep); truth["aug_total_all_lines"]=tot(aug); truth["oct_partial_total"]=tot(octo)
truth["sep_total_usage_only_wrong"]=tot(lambda r:sep(r) and r[3]=="Usage")
truth["sep_credit"]=-3000.0; truth["sep_tax"]=1240.55
truth["idle_eip_count"]=14; truth["idle_eip_monthly_sep"]=tot(lambda r:sep(r) and "IdleAddress" in r[5])
truth["sep_untagged_cost"]=tot(lambda r:sep(r) and r[11]=="")
truth["sep_total_for_untagged_share"]=tot(sep)
truth["oct_days"]=12
norm=lambda v: {"prod":"prod","Prod":"prod","production":"prod","dev":"dev","Dev":"dev","development":"dev"}.get(v,"")
truth["sep_prod_normalized"]=tot(lambda r:sep(r) and norm(r[11])=="prod")
truth["sep_dev_normalized"]=tot(lambda r:sep(r) and norm(r[11])=="dev")
truth["sep_untagged_share_pct"]=round(100*truth["sep_untagged_cost"]/truth["sep_total_for_untagged_share"],1)
truth["sep_minus_aug"]=round(truth["sep_total_all_lines"]-truth["aug_total_all_lines"],2)
json.dump(truth,open("truth.json","w"),indent=1)
print(json.dumps(truth,indent=1)); 
