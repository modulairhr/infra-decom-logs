# AWS Tagging Agent

## Purpose
The Tagging Agent applies preservation tags to resources that must be retained during the decommissioning process. This ensures critical infrastructure is not accidentally deleted.

## Tagging Strategy
Resources are tagged with:
- `decom:preserve=true` - Marks resource for preservation
- `decom:reason=<reason>` - Documents why the resource is preserved

## Preservation Criteria
Resources are preserved if they match any of these patterns:
- Control Tower resources (containing "ControlTower", "AWS-Landing-Zone")
- IAM resources (all roles, users, policies)
- AWS service-linked roles
- AWS SSO resources
- Organization management roles
- Route53 resources for modulairhr.com
- AWS Budgets and Savings Plans

## Supported Resource Types
- IAM roles, users, and policies
- S3 buckets
- CloudFormation stacks
- EC2 resources (VPCs, Security Groups)

## Running the Agent
```bash
python3 tagging_agent.py
```

## Output
Results are saved in the `results/` directory:
- Individual account tagging results: `tagging_{account_id}_{timestamp}.json`
- Summary report: `tagging_summary_{timestamp}.json`

## Important Notes
- The agent only tags resources for preservation
- No resources are deleted by this agent
- Failed tagging attempts are logged but don't stop the process
- Some resources may not support tagging (logged as failures)