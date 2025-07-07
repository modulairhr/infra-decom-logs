# AWS Infrastructure Decommissioning Log

## Mission
Decommission the AWS environment to the bare minimum while preserving critical infrastructure.

## Status
🔴 **IN PROGRESS** - Started: 2025-07-07

## Preserved Resources
- ✅ AWS Accounts (all profiles in ~/.aws/config)
- ✅ Landing Zone (Control Tower core resources)
- ✅ Organization Units (full OU hierarchy)
- ✅ IAM (roles, users, policies, permission boundaries)
- ✅ Route 53 (modulairhr.com domain and hosted zone)
- ✅ Billing & Support (Savings Plans, Reserved Instances, AWS Budgets)

## Agents Status

| Agent | Status | Last Updated | Notes |
|-------|--------|--------------|-------|
| Inventory | ✅ Complete | 2025-07-07 16:19 | Found 809 resources (581 to preserve, 228 to delete) |
| Tagging | ✅ Complete | 2025-07-07 16:25 | Tagged 447 resources for preservation |
| Sweeper-Account | 🟡 Starting | 2025-07-07 | Ready to begin cleanup |
| Sweeper-Region | ⏸️ Pending | - | Waiting for account cleanup |
| Auditor | ⏸️ Pending | - | Waiting for initial cleanup |

## Progress Tracking
- [x] GitHub repository created
- [x] Resource inventory completed (809 resources found)
- [x] Resources tagged for preservation (447 resources tagged)
- [ ] Non-essential resources removed
- [ ] Regions us-west-2 and us-east-1 disabled
- [ ] Final audit completed

## Directory Structure
```
/agents/
  /inventory/      # Inventory agent scripts and logs
  /sweeper-account/ # Account-level cleanup scripts
  /sweeper-region/  # Region-specific cleanup scripts
  /auditor/        # Validation and audit scripts
/logs/            # Real-time execution logs
/reports/         # Final compliance reports per account
```

## Quick Links
- [Inventory Results](./agents/inventory/README.md)
- [Account Status](./reports/account-status.md)
- [Audit Reports](./agents/auditor/reports/)
