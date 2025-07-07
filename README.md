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
| Inventory | 🟡 Starting | 2025-07-07 | Building resource map |
| Sweeper-Account | ⏸️ Pending | - | Waiting for inventory |
| Sweeper-Region | ⏸️ Pending | - | Waiting for inventory |
| Auditor | ⏸️ Pending | - | Waiting for initial scan |

## Progress Tracking
- [x] GitHub repository created
- [ ] Resource inventory completed
- [ ] Resources tagged for preservation
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
