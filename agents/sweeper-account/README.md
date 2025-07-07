# AWS Account Sweeper Agent

## ⚠️ CRITICAL WARNING ⚠️
This agent PERMANENTLY DELETES AWS resources. Use with extreme caution.

## Purpose
The Account Sweeper Agent removes all AWS resources that are NOT tagged with `decom:preserve=true`. This is the primary cleanup mechanism for decommissioning AWS accounts.

## Safety Features
1. **Dry Run Mode** (default): Shows what would be deleted without actually deleting
2. **Preservation Check**: Checks every resource for preservation tags before deletion
3. **Confirmation Required**: Live mode requires explicit confirmation
4. **Restricted Accounts**: Automatically skips LogArchive and Audit accounts in live mode
5. **Error Handling**: Continues on errors, logs all failures

## Running the Agent

### Dry Run (Safe - Default)
```bash
python3 account_sweeper_agent.py
```

### Specific Account Dry Run
```bash
python3 account_sweeper_agent.py --profile Development-Admin
```

### ⚠️ LIVE MODE - ACTUAL DELETION ⚠️
```bash
python3 account_sweeper_agent.py --live
```

### Live Mode for Specific Account
```bash
python3 account_sweeper_agent.py --live --profile Development-Admin
```

## Deletion Order
Resources are deleted in dependency order:
1. **Compute Resources**: Lambda functions, EC2 instances, RDS databases
2. **Storage Resources**: S3 buckets (with versioning cleanup)
3. **Infrastructure**: CloudFormation stacks

## Resources Deleted
- EC2 instances (with termination protection removal)
- Lambda functions
- RDS instances (with deletion protection removal)
- S3 buckets (including all versions and delete markers)
- CloudFormation stacks (except those tagged for preservation)

## Resources Preserved
Any resource with these tags is preserved:
- `decom:preserve=true`
- Resources that cannot be tagged assume preservation for safety

## Output
Results are saved in the `results/` directory:
- Individual account sweep logs: `sweep_{account_id}_{timestamp}.json`
- Summary report: `sweep_summary_{timestamp}.json`

## Verification
After running:
1. Check the summary report for deletion counts
2. Review failed deletions in the logs
3. Run the auditor agent to verify only preserved resources remain

## Common Issues
- **Access Denied**: Service Control Policies may prevent deletions
- **Dependency Errors**: Some resources may need manual deletion due to dependencies
- **Timeout**: Large CloudFormation stacks may take time to delete