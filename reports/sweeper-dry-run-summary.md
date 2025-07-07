# Account Sweeper Dry Run Summary
Generated: 2025-07-07 16:33:25 UTC

## Test Run: Development Account

The account sweeper was tested in dry-run mode on the Development account to validate its functionality before live execution.

### Results
- **Account**: Development-Admin (134388504287)
- **Mode**: DRY RUN (no actual deletions)
- **Resources that would be deleted**: 31
- **Resources preserved**: 11
- **Failures**: 0

### Resources Marked for Deletion
1. **Lambda Functions** (12 total):
   - Development tenant management functions
   - CloudFront log monitoring
   - Default security group remediation
   - Control Tower notification forwarders

2. **S3 Buckets** (3 total):
   - CDK asset buckets (us-east-2, us-west-2)
   - Tenant export bucket

3. **CloudFormation Stacks** (16 total):
   - SaaS platform stacks
   - GuardDuty stack
   - Cross-account roles
   - CDK toolkit stacks
   - Control Tower baseline stacks

### Resources Preserved
1. **Tagged Resources**:
   - modulairhr-marketing-dev S3 bucket (explicitly tagged)
   - Control Tower execution role stack

2. **System Resources** (preserved by default when tagging unavailable):
   - AWS Config buckets
   - SSM inventory buckets
   - CloudFront logs bucket
   - Lambda artifacts bucket

### Safety Features Validated
✅ Preservation tag checking works correctly
✅ Resources without accessible tags default to preservation
✅ Control Tower resources identified and preserved
✅ Dry run mode prevents any actual deletions

### Next Steps
With successful validation, the sweeper can be run in:
1. **Dry run mode** on all accounts to review full deletion plan
2. **Live mode** on non-production accounts first
3. **Live mode** on production accounts after verification