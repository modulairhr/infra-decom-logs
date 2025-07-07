#!/usr/bin/env python3
"""
AWS Account Sweeper Agent - Removes all resources NOT tagged for preservation
CRITICAL: This agent DELETES resources. Use with extreme caution.
"""

import json
import boto3
import time
from datetime import datetime
import os
import sys
from typing import Dict, List, Any, Set
import argparse

PRESERVE_TAG_KEY = "decom:preserve"
PRESERVE_TAG_VALUE = "true"
DRY_RUN = True  # Safety default - must explicitly set to False

# Service control policies may prevent deletion in these accounts
RESTRICTED_ACCOUNTS = ['LogArchive-Admin', 'Audit-Admin']

class AccountSweeperAgent:
    def __init__(self, profile_name: str, inventory_file: str, dry_run: bool = True):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.account_id = self.get_account_id()
        self.inventory = self.load_inventory(inventory_file)
        self.dry_run = dry_run
        self.deletion_log = {
            'account_id': self.account_id,
            'profile_name': profile_name,
            'start_time': datetime.utcnow().isoformat(),
            'dry_run': dry_run,
            'deletions': {
                'successful': [],
                'failed': [],
                'skipped_preserved': [],
                'skipped_dependency': []
            },
            'summary': {
                'total_deleted': 0,
                'total_failed': 0,
                'total_preserved': 0,
                'by_service': {}
            }
        }
        
    def get_account_id(self) -> str:
        try:
            sts = self.session.client('sts')
            return sts.get_caller_identity()['Account']
        except Exception as e:
            print(f"Error getting account ID: {e}")
            return "unknown"
    
    def load_inventory(self, inventory_file: str) -> Dict:
        """Load the inventory file for this account"""
        with open(inventory_file, 'r') as f:
            return json.load(f)
    
    def is_resource_preserved(self, resource_id: str, tags: List[Dict]) -> bool:
        """Check if a resource has the preservation tag"""
        if not tags:
            return False
        
        for tag in tags:
            if tag.get('Key') == PRESERVE_TAG_KEY and tag.get('Value') == PRESERVE_TAG_VALUE:
                return True
        return False
    
    def get_resource_tags(self, service_client, resource_arn: str = None, resource_id: str = None, 
                         resource_type: str = None) -> List[Dict]:
        """Get tags for a resource"""
        try:
            if resource_type == 's3':
                response = service_client.get_bucket_tagging(Bucket=resource_id)
                return response.get('TagSet', [])
            elif resource_type == 'ec2':
                response = service_client.describe_tags(
                    Filters=[{'Name': 'resource-id', 'Values': [resource_id]}]
                )
                return [{'Key': t['Key'], 'Value': t['Value']} for t in response.get('Tags', [])]
            elif resource_type == 'cloudformation':
                response = service_client.describe_stacks(StackName=resource_id)
                return response['Stacks'][0].get('Tags', [])
            elif resource_type == 'lambda':
                response = service_client.list_tags(Resource=resource_arn)
                return [{'Key': k, 'Value': v} for k, v in response.get('Tags', {}).items()]
            elif resource_type == 'rds':
                response = service_client.list_tags_for_resource(ResourceName=resource_arn)
                return response.get('TagList', [])
            else:
                return []
        except Exception as e:
            # If we can't get tags, assume resource should be preserved for safety
            print(f"    Warning: Could not get tags for {resource_id}: {e}")
            return [{'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE}]  # Safety default
    
    def delete_s3_buckets(self):
        """Delete S3 buckets not tagged for preservation"""
        if 's3_buckets' not in self.inventory['regions'].get('us-east-1', {}).get('resources', {}):
            return
            
        print(f"  Processing S3 buckets...")
        s3 = self.session.client('s3')
        
        buckets = self.inventory['regions']['us-east-1']['resources']['s3_buckets'].get('resources', [])
        for bucket in buckets:
            bucket_name = bucket['Name']
            
            try:
                tags = self.get_resource_tags(s3, resource_id=bucket_name, resource_type='s3')
                
                if self.is_resource_preserved(bucket_name, tags):
                    print(f"    PRESERVED: S3 bucket {bucket_name}")
                    self.deletion_log['deletions']['skipped_preserved'].append({
                        'type': 's3_bucket',
                        'id': bucket_name,
                        'reason': 'Tagged for preservation'
                    })
                    self.deletion_log['summary']['total_preserved'] += 1
                else:
                    if self.dry_run:
                        print(f"    DRY RUN - Would delete: S3 bucket {bucket_name}")
                    else:
                        # Empty bucket first
                        print(f"    Emptying S3 bucket {bucket_name}...")
                        paginator = s3.get_paginator('list_object_versions')
                        
                        delete_markers = []
                        versions = []
                        
                        for page in paginator.paginate(Bucket=bucket_name):
                            for marker in page.get('DeleteMarkers', []):
                                delete_markers.append({'Key': marker['Key'], 'VersionId': marker['VersionId']})
                            for version in page.get('Versions', []):
                                versions.append({'Key': version['Key'], 'VersionId': version['VersionId']})
                        
                        # Delete all versions and markers
                        for i in range(0, len(delete_markers), 1000):
                            batch = delete_markers[i:i+1000]
                            if batch:
                                s3.delete_objects(Bucket=bucket_name, Delete={'Objects': batch})
                        
                        for i in range(0, len(versions), 1000):
                            batch = versions[i:i+1000]
                            if batch:
                                s3.delete_objects(Bucket=bucket_name, Delete={'Objects': batch})
                        
                        # Delete bucket
                        s3.delete_bucket(Bucket=bucket_name)
                        print(f"    DELETED: S3 bucket {bucket_name}")
                        
                    self.deletion_log['deletions']['successful'].append({
                        'type': 's3_bucket',
                        'id': bucket_name
                    })
                    self.deletion_log['summary']['total_deleted'] += 1
                    
            except Exception as e:
                print(f"    ERROR deleting S3 bucket {bucket_name}: {e}")
                self.deletion_log['deletions']['failed'].append({
                    'type': 's3_bucket',
                    'id': bucket_name,
                    'error': str(e)
                })
                self.deletion_log['summary']['total_failed'] += 1
    
    def delete_cloudformation_stacks(self, region: str):
        """Delete CloudFormation stacks not tagged for preservation"""
        if 'cloudformation_stacks' not in self.inventory['regions'].get(region, {}).get('resources', {}):
            return
            
        print(f"    Processing CloudFormation stacks in {region}...")
        cfn = self.session.client('cloudformation', region_name=region)
        
        stacks = self.inventory['regions'][region]['resources']['cloudformation_stacks'].get('resources', [])
        
        # Sort stacks to delete non-Control Tower stacks first
        def stack_priority(stack):
            name = stack['StackName'].lower()
            if 'controltower' in name or 'landing-zone' in name:
                return 2  # Process last
            elif 'cdk-' in name:
                return 1  # Process second
            else:
                return 0  # Process first
        
        stacks.sort(key=stack_priority)
        
        for stack in stacks:
            stack_name = stack['StackName']
            
            try:
                tags = self.get_resource_tags(cfn, resource_id=stack_name, resource_type='cloudformation')
                
                if self.is_resource_preserved(stack_name, tags):
                    print(f"      PRESERVED: Stack {stack_name}")
                    self.deletion_log['deletions']['skipped_preserved'].append({
                        'type': 'cloudformation_stack',
                        'id': stack_name,
                        'region': region,
                        'reason': 'Tagged for preservation'
                    })
                    self.deletion_log['summary']['total_preserved'] += 1
                else:
                    if self.dry_run:
                        print(f"      DRY RUN - Would delete: Stack {stack_name}")
                    else:
                        # Check if stack has termination protection
                        stack_details = cfn.describe_stacks(StackName=stack_name)['Stacks'][0]
                        if stack_details.get('EnableTerminationProtection', False):
                            cfn.update_termination_protection(
                                StackName=stack_name,
                                EnableTerminationProtection=False
                            )
                        
                        cfn.delete_stack(StackName=stack_name)
                        print(f"      DELETING: Stack {stack_name}")
                        
                        # Wait for deletion to complete (with timeout)
                        waiter = cfn.get_waiter('stack_delete_complete')
                        try:
                            waiter.wait(
                                StackName=stack_name,
                                WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
                            )
                            print(f"      DELETED: Stack {stack_name}")
                        except:
                            print(f"      WARNING: Stack {stack_name} deletion still in progress")
                            
                    self.deletion_log['deletions']['successful'].append({
                        'type': 'cloudformation_stack',
                        'id': stack_name,
                        'region': region
                    })
                    self.deletion_log['summary']['total_deleted'] += 1
                    
            except Exception as e:
                print(f"      ERROR deleting stack {stack_name}: {e}")
                self.deletion_log['deletions']['failed'].append({
                    'type': 'cloudformation_stack',
                    'id': stack_name,
                    'region': region,
                    'error': str(e)
                })
                self.deletion_log['summary']['total_failed'] += 1
    
    def delete_lambda_functions(self, region: str):
        """Delete Lambda functions not tagged for preservation"""
        if 'lambda_functions' not in self.inventory['regions'].get(region, {}).get('resources', {}):
            return
            
        print(f"    Processing Lambda functions in {region}...")
        lambda_client = self.session.client('lambda', region_name=region)
        
        functions = self.inventory['regions'][region]['resources']['lambda_functions'].get('resources', [])
        for function in functions:
            function_name = function['FunctionName']
            
            try:
                # Get function ARN for tagging
                func_details = lambda_client.get_function(FunctionName=function_name)
                function_arn = func_details['Configuration']['FunctionArn']
                
                tags = self.get_resource_tags(lambda_client, resource_arn=function_arn, resource_type='lambda')
                
                if self.is_resource_preserved(function_name, tags):
                    print(f"      PRESERVED: Lambda function {function_name}")
                    self.deletion_log['deletions']['skipped_preserved'].append({
                        'type': 'lambda_function',
                        'id': function_name,
                        'region': region,
                        'reason': 'Tagged for preservation'
                    })
                    self.deletion_log['summary']['total_preserved'] += 1
                else:
                    if self.dry_run:
                        print(f"      DRY RUN - Would delete: Lambda function {function_name}")
                    else:
                        lambda_client.delete_function(FunctionName=function_name)
                        print(f"      DELETED: Lambda function {function_name}")
                        
                    self.deletion_log['deletions']['successful'].append({
                        'type': 'lambda_function',
                        'id': function_name,
                        'region': region
                    })
                    self.deletion_log['summary']['total_deleted'] += 1
                    
            except Exception as e:
                print(f"      ERROR deleting Lambda function {function_name}: {e}")
                self.deletion_log['deletions']['failed'].append({
                    'type': 'lambda_function',
                    'id': function_name,
                    'region': region,
                    'error': str(e)
                })
                self.deletion_log['summary']['total_failed'] += 1
    
    def delete_rds_resources(self, region: str):
        """Delete RDS resources not tagged for preservation"""
        regional_resources = self.inventory['regions'].get(region, {}).get('resources', {})
        
        if not any(key.startswith('rds_') for key in regional_resources):
            return
            
        print(f"    Processing RDS resources in {region}...")
        rds = self.session.client('rds', region_name=region)
        
        # Delete DB instances
        if 'rds_instances' in regional_resources:
            for db in regional_resources['rds_instances'].get('resources', []):
                db_id = db['DBInstanceIdentifier']
                
                try:
                    db_details = rds.describe_db_instances(DBInstanceIdentifier=db_id)['DBInstances'][0]
                    db_arn = db_details['DBInstanceArn']
                    
                    tags = self.get_resource_tags(rds, resource_arn=db_arn, resource_type='rds')
                    
                    if self.is_resource_preserved(db_id, tags):
                        print(f"      PRESERVED: RDS instance {db_id}")
                        self.deletion_log['deletions']['skipped_preserved'].append({
                            'type': 'rds_instance',
                            'id': db_id,
                            'region': region,
                            'reason': 'Tagged for preservation'
                        })
                        self.deletion_log['summary']['total_preserved'] += 1
                    else:
                        if self.dry_run:
                            print(f"      DRY RUN - Would delete: RDS instance {db_id}")
                        else:
                            # Disable deletion protection if enabled
                            if db_details.get('DeletionProtection', False):
                                rds.modify_db_instance(
                                    DBInstanceIdentifier=db_id,
                                    DeletionProtection=False,
                                    ApplyImmediately=True
                                )
                                time.sleep(10)  # Wait for modification
                            
                            rds.delete_db_instance(
                                DBInstanceIdentifier=db_id,
                                SkipFinalSnapshot=True,
                                DeleteAutomatedBackups=True
                            )
                            print(f"      DELETED: RDS instance {db_id}")
                            
                        self.deletion_log['deletions']['successful'].append({
                            'type': 'rds_instance',
                            'id': db_id,
                            'region': region
                        })
                        self.deletion_log['summary']['total_deleted'] += 1
                        
                except Exception as e:
                    print(f"      ERROR deleting RDS instance {db_id}: {e}")
                    self.deletion_log['deletions']['failed'].append({
                        'type': 'rds_instance',
                        'id': db_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.deletion_log['summary']['total_failed'] += 1
    
    def delete_ec2_resources(self, region: str):
        """Delete EC2 resources not tagged for preservation"""
        regional_resources = self.inventory['regions'].get(region, {}).get('resources', {})
        
        if not any(key in ['ec2_instances', 'vpcs', 'security_groups'] for key in regional_resources):
            return
            
        print(f"    Processing EC2 resources in {region}...")
        ec2 = self.session.client('ec2', region_name=region)
        
        # Delete EC2 instances first
        if 'ec2_instances' in regional_resources:
            reservations = regional_resources['ec2_instances'].get('resources', [])
            for reservation in reservations:
                for instance in reservation.get('Instances', []):
                    instance_id = instance['InstanceId']
                    
                    try:
                        tags = self.get_resource_tags(ec2, resource_id=instance_id, resource_type='ec2')
                        
                        if self.is_resource_preserved(instance_id, tags):
                            print(f"      PRESERVED: EC2 instance {instance_id}")
                            self.deletion_log['deletions']['skipped_preserved'].append({
                                'type': 'ec2_instance',
                                'id': instance_id,
                                'region': region,
                                'reason': 'Tagged for preservation'
                            })
                            self.deletion_log['summary']['total_preserved'] += 1
                        else:
                            if self.dry_run:
                                print(f"      DRY RUN - Would terminate: EC2 instance {instance_id}")
                            else:
                                # Check if instance has termination protection
                                attrs = ec2.describe_instance_attribute(
                                    InstanceId=instance_id,
                                    Attribute='disableApiTermination'
                                )
                                if attrs.get('DisableApiTermination', {}).get('Value', False):
                                    ec2.modify_instance_attribute(
                                        InstanceId=instance_id,
                                        DisableApiTermination={'Value': False}
                                    )
                                
                                ec2.terminate_instances(InstanceIds=[instance_id])
                                print(f"      TERMINATED: EC2 instance {instance_id}")
                                
                            self.deletion_log['deletions']['successful'].append({
                                'type': 'ec2_instance',
                                'id': instance_id,
                                'region': region
                            })
                            self.deletion_log['summary']['total_deleted'] += 1
                            
                    except Exception as e:
                        print(f"      ERROR terminating EC2 instance {instance_id}: {e}")
                        self.deletion_log['deletions']['failed'].append({
                            'type': 'ec2_instance',
                            'id': instance_id,
                            'region': region,
                            'error': str(e)
                        })
                        self.deletion_log['summary']['total_failed'] += 1
    
    def sweep_account(self):
        """Main sweeping execution"""
        print(f"\nSweeping account {self.account_id} ({self.profile_name})")
        if self.dry_run:
            print("*** DRY RUN MODE - No resources will be deleted ***")
        else:
            print("*** LIVE MODE - Resources WILL be deleted ***")
            
        # Skip restricted accounts in live mode
        if not self.dry_run and self.profile_name in RESTRICTED_ACCOUNTS:
            print(f"  SKIPPING {self.profile_name} - Service Control Policies prevent deletions")
            self.deletion_log['summary']['skip_reason'] = 'Service Control Policies'
            return self.deletion_log
        
        # Delete resources in order of dependency
        # 1. First delete compute resources
        for region in self.inventory.get('regions', {}):
            self.delete_lambda_functions(region)
            self.delete_ec2_resources(region)
            self.delete_rds_resources(region)
        
        # 2. Delete storage resources
        self.delete_s3_buckets()
        
        # 3. Delete infrastructure resources
        for region in self.inventory.get('regions', {}):
            self.delete_cloudformation_stacks(region)
        
        self.deletion_log['end_time'] = datetime.utcnow().isoformat()
        
        # Save results
        output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/sweeper-account/results"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/sweep_{self.account_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.deletion_log, f, indent=2)
        
        print(f"\nSweep complete for account {self.account_id}")
        print(f"  Resources deleted: {self.deletion_log['summary']['total_deleted']}")
        print(f"  Resources preserved: {self.deletion_log['summary']['total_preserved']}")
        print(f"  Failures: {self.deletion_log['summary']['total_failed']}")
        print(f"  Results saved to: {filename}")
        
        return self.deletion_log


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='AWS Account Sweeper Agent')
    parser.add_argument('--live', action='store_true', help='Run in LIVE mode (actually delete resources)')
    parser.add_argument('--profile', type=str, help='Specific AWS profile to sweep')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt (use with caution!)')
    args = parser.parse_args()
    
    dry_run = not args.live
    
    print("AWS Account Sweeper Agent Starting...")
    print(f"Mode: {'LIVE - RESOURCES WILL BE DELETED' if not dry_run else 'DRY RUN - No deletions'}")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    
    if not dry_run and not args.force:
        response = input("\n⚠️  WARNING: Live mode will DELETE resources! Type 'DELETE' to confirm: ")
        if response != 'DELETE':
            print("Confirmation not received. Exiting.")
            sys.exit(1)
    elif not dry_run and args.force:
        print("\n⚠️  WARNING: Live mode with --force flag. Resources WILL BE DELETED!")
    
    # Load consolidated inventory
    inventory_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/inventory/results"
    consolidated_file = None
    
    for file in os.listdir(inventory_dir):
        if file.startswith('consolidated_inventory_'):
            consolidated_file = os.path.join(inventory_dir, file)
            break
    
    if not consolidated_file:
        print("Error: No consolidated inventory found!")
        sys.exit(1)
    
    with open(consolidated_file, 'r') as f:
        consolidated = json.load(f)
    
    all_results = {}
    
    # Process specified profile or all profiles
    profiles_to_process = [args.profile] if args.profile else consolidated['accounts'].keys()
    
    for profile in profiles_to_process:
        if profile not in consolidated['accounts']:
            print(f"Error: Profile {profile} not found in inventory")
            continue
            
        try:
            print(f"\nProcessing {profile}...")
            account_data = consolidated['accounts'][profile]
            agent = AccountSweeperAgent(profile, account_data['inventory_file'], dry_run)
            results = agent.sweep_account()
            all_results[profile] = results
        except Exception as e:
            print(f"Error processing {profile}: {e}")
            all_results[profile] = {'error': str(e)}
    
    # Generate summary report
    summary = {
        'execution_time': datetime.utcnow().isoformat(),
        'mode': 'DRY_RUN' if dry_run else 'LIVE',
        'accounts_processed': len(all_results),
        'total_deleted': sum(r.get('summary', {}).get('total_deleted', 0) for r in all_results.values()),
        'total_preserved': sum(r.get('summary', {}).get('total_preserved', 0) for r in all_results.values()),
        'total_failed': sum(r.get('summary', {}).get('total_failed', 0) for r in all_results.values()),
        'by_account': {}
    }
    
    for profile, results in all_results.items():
        if 'error' in results:
            summary['by_account'][profile] = {'status': 'error', 'error': results['error']}
        else:
            summary['by_account'][profile] = {
                'status': 'success',
                'deleted': results.get('summary', {}).get('total_deleted', 0),
                'preserved': results.get('summary', {}).get('total_preserved', 0),
                'failed': results.get('summary', {}).get('total_failed', 0),
                'skip_reason': results.get('summary', {}).get('skip_reason')
            }
    
    # Save summary
    output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/sweeper-account/results"
    summary_file = f"{output_dir}/sweep_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n\nAccount Sweeper Complete!")
    print(f"Summary saved to: {summary_file}")
    print(f"Mode: {summary['mode']}")
    print(f"Total resources deleted: {summary['total_deleted']}")
    print(f"Total resources preserved: {summary['total_preserved']}")
    print(f"Total failures: {summary['total_failed']}")


if __name__ == "__main__":
    main()