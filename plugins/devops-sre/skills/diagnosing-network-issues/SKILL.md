---
name: diagnosing-network-issues
description: Layer-by-layer network troubleshooting for DNS, TCP connectivity, TLS, HTTP, MTU and Kubernetes pod networking. Use when a service is unreachable, slow, times out, returns certificate errors, or a pod cannot resolve or reach another service.
---

# Diagnosing network issues

Walk the stack bottom-up and stop at the first layer that fails. Record each result; do not guess.

## Workflow

```
- [ ] 1. Define: source, destination (name + IP + port), protocol, since when
- [ ] 2. DNS
- [ ] 3. Reachability (route, TCP)
- [ ] 4. TLS
- [ ] 5. HTTP / application
- [ ] 6. Path details (MTU, firewall, NAT)
```

**2. DNS**
```bash
dig +short NAME                 # what the local resolver says
dig NAME @1.1.1.1               # compare with a public resolver
dig +trace NAME                 # delegation chain; finds broken NS
dig +tcp NAME                   # if UDP is blocked or truncated
```
Different answers between resolvers = caching, split-horizon, or a recent change (check TTL).

**3. Reachability**
```bash
nc -zv HOST PORT                # TCP connect: open / refused / timeout
mtr -rwzc 50 HOST               # loss and latency per hop
ss -tlnp | grep PORT            # on the server: is anything listening, on which address?
```
- **refused** = host reachable, nothing listening (or reject rule). **timeout** = packets dropped (firewall, security group, route).
- Listening only on `127.0.0.1` explains "works locally, not remotely".

**4. TLS**
```bash
openssl s_client -connect HOST:443 -servername HOST </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```
Check expiry, SAN match, full chain (intermediate missing is common), and SNI (`-servername`).

**5. HTTP**
```bash
curl -sv --connect-timeout 5 --max-time 15 https://HOST/path -o /dev/null
curl -sv --resolve HOST:443:IP https://HOST/     # bypass DNS to test one backend
curl -w 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' -so /dev/null https://HOST/
```
The timing line shows which phase is slow.

**6. Path details**
- MTU/fragmentation (hangs on large payloads, small ones work): `ping -M do -s 1472 HOST` on Linux (`ping -D -s 1472` on macOS); reduce size until it passes.
- Capture when unsure: `sudo tcpdump -ni any host IP and port PORT`. SYN with no SYN-ACK = dropped upstream; RST = refused.
- Cloud: check security group / firewall rule, route table, NACL, and egress NAT before blaming the app.

## Kubernetes
```bash
kubectl run dbg -it --rm --image=nicolaka/netshoot --restart=Never -- bash
# inside: dig kubernetes.default.svc.cluster.local ; curl -sv http://SVC.NS.svc:PORT
kubectl -n kube-system logs -l k8s-app=kube-dns --tail=50
kubectl get endpoints SVC -n NS          # empty endpoints = selector/readiness problem, not network
kubectl get networkpolicy -A
```
- Service has no endpoints → label selector mismatch or pods not Ready.
- Default pod `ndots:5` makes short external names try several search domains first; use FQDN with trailing dot for external lookups when DNS is slow.
- NetworkPolicy default-deny silently drops: list policies in both source and destination namespaces.

## Do not
- Declare a root cause from one layer's success; a working DNS says nothing about the firewall.
- Run packet captures on production hosts without saying what is captured and for how long.
