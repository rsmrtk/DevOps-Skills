---
name: operating-patroni-consul
description: Diagnoses and operates Patroni PostgreSQL HA clusters backed by Consul or built-in Raft as the DCS. Covers failover timing, loss of DCS quorum, ttl/loop_wait/retry_timeout tuning, Consul ACL tokens for Patroni, DNS and client caching, and safe patronictl operations. Use when a primary is demoted or unreachable, failover is slow, Patroni logs "DCS is not accessible", Consul returns 403 or "No cluster leader", or someone proposes tuning Patroni timings.
---

# Operating Patroni with Consul (or Raft) as DCS

Postgres has no quorum of its own. Split-brain safety rests entirely on the DCS, so the DCS must be at least as reliable as the write SLA of the database.

## Mental model
- The primary holds a **leader key with TTL** (`ttl`), refreshed every `loop_wait`. If the refresh stops, the key expires and replicas elect a new primary. Only one node can create the key (compare-and-set), which prevents two primaries.
- With **Consul** the key lives under `service/<scope>/`, bound to a Consul session. Patroni also registers the service with tags (`primary`/`master`, `replica`) and a health check on REST port 8008, which gives DNS names such as `master.<scope>.service.consul`.
- With **built-in Raft** the quorum is the Postgres nodes themselves. There is no service registry or DNS: clients need HAProxy/pgbouncer/VIP with checks on `GET :8008/primary`, or libpq `target_session_attrs=read-write`. Two nodes give no fault tolerance; use at least three.

## Behaviour measured in a lab (Consul DCS, ttl=30, loop_wait=10, retry_timeout=10)
| Event | Observed |
|---|---|
| Graceful stop of primary | new leader in ~8 s (Patroni releases the key on shutdown) |
| Hard kill of primary | new leader in ~25 s (wait for session/TTL expiry); `master` DNS briefly empty |
| Loss of Consul quorum (2 of 3 servers down) | primary demoted after ~15–30 s, `pg_is_in_recovery = t`, `/primary` returns 503, writes impossible |
| Consul servers return | cluster re-forms by itself, timeline increments |
Same demotion happens with built-in Raft when a majority of nodes is lost. This is the designed trade: safer to stop writes than to risk split-brain. Do not "fix" it by promoting manually.

## Triage: primary demoted or writes failing
```
- [ ] 1. patronictl -c <cfg> list            # roles, timeline, lag
- [ ] 2. Patroni log: "DCS is not accessible"?   # DCS problem, not a Postgres problem
- [ ] 3. Consul: consul operator raft list-peers  # quorum? how many servers alive
- [ ] 4. ACL: is Patroni's token allowed? (403 in Patroni log)
- [ ] 5. Network: agent <-> servers (8300/8301), local agent healthy
- [ ] 6. Only then Postgres itself: curl localhost:8008/health
```
If Consul has no leader, restore Consul quorum first. Stale reads (`?stale`) still work while writes do not.

## Timings: do not tune casually
- `ttl` is the **maximum time to detect a dead primary**. Lowering it makes failover faster and false demotions more likely.
- Keep `loop_wait + 2 * retry_timeout <= ttl`, otherwise switchovers become unstable.
- `maximum_lag_on_failover` blocks promotion of a replica lagging more than the limit.
- `synchronous_mode: true` avoids losing acknowledged transactions at the cost of write latency.
- `failsafe_mode` (Patroni 3.0+) lets a primary stay primary without the DCS while it can reach all members. It is a safety trade-off, **not verified in the lab**: read the docs for your version before proposing it.
- Change one parameter at a time, and rehearse in a lab before production.

## Consul ACL for Patroni
Symptoms and fixes seen in the lab (Consul 2.x):
| Symptom | Cause | Fix |
|---|---|---|
| Patroni gets 403 from Consul | token lacks prefixes | policy with `key_prefix "service/"` (write), `session_prefix ""` (write), `service_prefix ""` (write) |
| DNS returns nothing after `default_policy = deny` | agent has no `default` token with read | set `tokens { default = ... }` |
| Service from a config file refused: lacks `service:write` | registered with the agent's default token | put `token = "..."` inside the `service {}` block |
Hand out tokens to health checks and monitoring **before** switching to deny.

## Clients and DNS
Clients with a long DNS cache keep connecting to the old primary after a switch. Lower the TTL, retry on failure, and register IPs rather than hostnames (a hostname becomes a CNAME and may return one address).

## patronictl: what changes things
Read-only: `list`, `show-config`, REST `GET /health`, `GET /`. These need no approval.
Needs a plan and approval: `switchover` (planned), `failover` (when no leader), `restart`, `edit-config`, `pause`/`resume`, and **`reinit`, which wipes the replica's data directory and reclones it**.
Before maintenance use `pause` to stop automatic failover, and `resume` afterwards; state the resume step in the plan.

## Do not
- Promote a node by hand, or remove the leader key in the DCS, to "get writes back" before checking DCS quorum.
- Lower `ttl` or `retry_timeout` to speed up failover without the `loop_wait + 2 * retry_timeout <= ttl` check and a rehearsal.
- State a failover time as fact for the user's cluster; the figures above are from a lab with these exact settings.
