# AWS cost reference

Read-only commands are templates; check `--help`. Cost Explorer API calls are billed per request.

## Where the money is: find it first
```bash
# by service, last full month
aws ce get-cost-and-usage --time-period Start=YYYY-MM-01,End=YYYY-MM-01 \
  --granularity MONTHLY --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
# then drill: Key=USAGE_TYPE (NatGateway-Bytes, DataTransfer-Regional-Bytes, BoxUsage ...)
```
Tools: Cost Explorer, Data Exports (CUR 2.0) to S3/Athena for line-level analysis, Cost Anomaly
Detection, Budgets, Compute Optimizer, Cost Optimization Hub, Trusted Advisor. Cost allocation tags
must be **activated** in the Billing console before they appear in reports, and are not retroactive.
Enumerate all accounts through AWS Organizations and all regions (`aws ec2 describe-regions`).

## Compute (EC2, Fargate, Lambda)
- **Commitments:** Compute Savings Plans (flexible across instance family, region, OS; cover Fargate and Lambda) vs EC2 Instance Savings Plans (family + region, deeper discount) vs Reserved Instances. See `commitments.md`.
- **Spot:** large discount (AWS documents up to about 90%) for restartable work. Use many instance types and AZs, capacity-optimized allocation, handle the 2-minute interruption notice. Not for single-replica stateful services.
- **Graviton (arm64):** usually better price/performance. Requires arm64 builds; test, do not flip blindly.
- **Rightsizing:** Compute Optimizer recommendations need about 14 days of metrics and do not see memory unless the CloudWatch agent is installed. Check memory before downsizing.
- Previous-generation instance types and `gp2`/`io1` are common easy upgrades.
- Dev/test: schedule stop/start (Instance Scheduler or automation). A stopped instance still pays for its EBS volumes and Elastic IP.
- **Lambda:** arm64, right memory (power tuning: more memory can be cheaper by finishing faster), avoid idle provisioned concurrency, set log retention.
- **Fargate** costs more per vCPU/GB than EC2 you keep well packed; it wins when utilization of your own nodes would be low.

## Storage
- **EBS:** migrate gp2 to gp3 (cheaper per GB, baseline IOPS/throughput not tied to size; can be done online). Find unattached (`status=available`) volumes. Old snapshots: Data Lifecycle Manager policies, snapshot Archive tier for rarely restored.
  ```bash
  aws ec2 describe-volumes --filters Name=volume-type,Values=gp2 --query 'Volumes[].[VolumeId,Size]' --output text
  aws ec2 describe-snapshots --owner-ids self --query 'Snapshots[?StartTime<=`2025-01-01`].[SnapshotId,VolumeSize,StartTime]'
  ```
- **S3:** lifecycle rules for tiering and expiration; abort incomplete multipart uploads; expire noncurrent versions; Intelligent-Tiering for unknown access patterns (per-object monitoring fee; small objects are not auto-tiered); Storage Lens for the biggest buckets. Colder classes have **minimum storage durations** and minimum billable object sizes, so moving short-lived or tiny objects can cost more. Request charges can dominate with many small objects.
- **EFS:** lifecycle to IA, One Zone for non-critical data.
- **Backups:** AWS Backup retention, cross-region copies you no longer need.

## Network and data transfer (the usual surprise)
- **NAT Gateway:** hourly plus per-GB processing. Biggest culprit is traffic to S3/DynamoDB/ECR through NAT. Add free **gateway VPC endpoints** for S3 and DynamoDB; use interface endpoints (hourly charge) only where volume justifies them. One NAT per AZ for availability, but non-prod can share.
- **Cross-AZ traffic** is charged in both directions. Chatty services, Kafka/DB replication, and load balancer cross-zone settings add up. Prefer same-AZ routing where it does not hurt availability.
- **Public IPv4 addresses** are billed hourly (in-use and idle). Remove idle Elastic IPs, consider IPv6 and shared ingress.
- Internet egress: CloudFront in front of S3/ALB is often cheaper than direct egress and offloads origins.
- Cross-region replication and inter-region transfer: confirm it is needed.
  ```bash
  aws ec2 describe-nat-gateways --query 'NatGateways[].[NatGatewayId,VpcId,State]'
  aws ec2 describe-addresses --query 'Addresses[?AssociationId==`null`]'
  ```

## Databases
- **RDS/Aurora:** rightsize from CPU, memory and connections; Multi-AZ doubles cost, so question it in non-prod. Aurora **I/O-Optimized** can be cheaper when I/O is a large share of the Aurora bill (compare against Standard with your real I/O). Stop dev databases (RDS auto-starts them after 7 days; automate). Delete manual snapshots you do not need. Reserved Instances for RDS apply by engine/class/region.
- **DynamoDB:** on-demand vs provisioned with autoscaling by traffic shape; Standard-IA table class for rarely read big tables; TTL for expiring data.
- **ElastiCache/OpenSearch:** often over-provisioned; check memory headroom and node counts.

## Observability and logging
- **CloudWatch Logs:** default retention is never expire. Set retention on every group; ingestion is the main cost, so cut verbose debug logs at the source; consider the Infrequent Access log class.
  ```bash
  aws logs describe-log-groups --query 'logGroups[?retentionInDays==`null`].[logGroupName,storedBytes]' --output text
  ```
- Custom metrics and high-cardinality dimensions, detailed monitoring, Container Insights, and X-Ray sampling are billed per unit. Check what is enabled everywhere.

## Containers (EKS/ECS)
- EKS control plane has an hourly fee per cluster; clusters on out-of-standard-support Kubernetes versions pay an extended-support surcharge. Consolidate tiny clusters, upgrade old ones.
- Karpenter or Cluster Autoscaler with consolidation, Spot node pools, Graviton nodes. See `kubernetes.md`.
- ECR lifecycle policies to expire untagged and old images. Pull through a regional endpoint to avoid NAT traffic.

## Idle resources checklist
Unattached EBS, old snapshots and AMIs, idle ALB/NLB (no healthy targets or near-zero requests), unused Elastic IPs, NAT in empty VPCs, idle RDS, unused Savings Plan (low utilization), CloudWatch log groups without retention, old ECR images, forgotten dev stacks (use tags + Resource Explorer).
