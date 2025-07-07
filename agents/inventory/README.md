# AWS Inventory Agent

## Purpose
The Inventory Agent performs comprehensive resource discovery across all AWS accounts and regions to create a complete map of existing infrastructure.

## Features
- Parallel scanning of all AWS regions
- Identification of resources to preserve (Control Tower, IAM, Route53, etc.)
- Detailed inventory by service and region
- Consolidated reporting across all accounts

## Resources Preserved
The agent automatically marks the following resource types for preservation:
- AWS Organizations accounts and OUs
- Control Tower landing zone resources
- All IAM roles, users, and policies
- Route53 hosted zones for modulairhr.com
- AWS Budgets and Savings Plans
- Support plan configurations

## Output
Results are saved in the `results/` directory:
- Individual account inventories: `inventory_{account_id}_{timestamp}.json`
- Consolidated report: `consolidated_inventory_{timestamp}.json`

## Running the Agent
```bash
python3 inventory_agent.py
```

## Inventory Structure
Each account inventory includes:
- Global resources (IAM, Route53, Organizations)
- Regional resources by service
- Summary statistics
- Resources marked for preservation

## Next Steps
After inventory completion:
1. Review consolidated report
2. Verify preservation tags
3. Proceed with account sweeper agents