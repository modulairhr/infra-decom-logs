#!/usr/bin/env python3
"""
AWS Tagging Agent - Tags resources for preservation during decommissioning
"""

import json
import boto3
import concurrent.futures
from datetime import datetime
import os
import sys
from typing import Dict, List, Any, Set

PRESERVE_TAG_KEY = "decom:preserve"
PRESERVE_TAG_VALUE = "true"
PRESERVE_REASON_KEY = "decom:reason"

# Resources that should be preserved
PRESERVE_PATTERNS = {
    'ControlTower': 'AWS Control Tower landing zone resource',
    'AWS-Landing-Zone': 'AWS Landing Zone resource', 
    'AWSControlTower': 'Control Tower managed resource',
    'aws-controltower': 'Control Tower managed resource',
    'OrganizationAccountAccessRole': 'Organization management role',
    'AWSReservedSSO': 'AWS SSO managed resource',
    'AWS-SystemsManager': 'AWS Systems Manager resource',
    'aws-service-role': 'AWS service-linked role',
    'modulairhr.com': 'Company domain resource',
    'ModulairHR': 'Company resource',
    'aws-budgets': 'AWS Budgets resource',
    'savings-plan': 'Savings Plan resource',
}

class AWSTaggingAgent:
    def __init__(self, profile_name: str, inventory_file: str):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.account_id = self.get_account_id()
        self.inventory = self.load_inventory(inventory_file)
        self.tagging_results = {
            'account_id': self.account_id,
            'profile_name': profile_name,
            'start_time': datetime.utcnow().isoformat(),
            'resources_tagged': 0,
            'resources_failed': 0,
            'by_service': {},
            'errors': []
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
    
    def should_preserve_resource(self, resource_name: str, resource_type: str = None) -> tuple[bool, str]:
        """Determine if a resource should be preserved based on patterns"""
        # Check resource name against patterns
        for pattern, reason in PRESERVE_PATTERNS.items():
            if pattern.lower() in resource_name.lower():
                return True, reason
        
        # Check specific resource types
        if resource_type:
            if resource_type in ['AWS::IAM::Role', 'AWS::IAM::User', 'AWS::IAM::Policy']:
                return True, 'IAM resource - preserve all'
            if resource_type.startswith('AWS::Organizations::'):
                return True, 'Organizations resource'
            if resource_type.startswith('AWS::ControlTower::'):
                return True, 'Control Tower resource'
            if resource_type.startswith('AWS::Route53::'):
                if 'modulairhr.com' in resource_name.lower():
                    return True, 'Company domain resource'
        
        return False, ''
    
    def tag_iam_resources(self):
        """Tag IAM resources for preservation"""
        print(f"  Tagging IAM resources...")
        iam = self.session.client('iam')
        
        # Tag IAM roles
        if 'iam_roles' in self.inventory.get('global_resources', {}):
            roles = self.inventory['global_resources']['iam_roles'].get('resources', [])
            for role in roles:
                try:
                    preserve, reason = self.should_preserve_resource(role['RoleName'], 'AWS::IAM::Role')
                    if preserve:
                        iam.tag_role(
                            RoleName=role['RoleName'],
                            Tags=[
                                {'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE},
                                {'Key': PRESERVE_REASON_KEY, 'Value': reason}
                            ]
                        )
                        self.tagging_results['resources_tagged'] += 1
                        print(f"    Tagged role: {role['RoleName']}")
                except Exception as e:
                    self.tagging_results['resources_failed'] += 1
                    self.tagging_results['errors'].append(f"Failed to tag role {role['RoleName']}: {str(e)}")
        
        # Tag IAM users
        if 'iam_users' in self.inventory.get('global_resources', {}):
            users = self.inventory['global_resources']['iam_users'].get('resources', [])
            for user in users:
                try:
                    preserve, reason = self.should_preserve_resource(user['UserName'], 'AWS::IAM::User')
                    if preserve:
                        iam.tag_user(
                            UserName=user['UserName'],
                            Tags=[
                                {'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE},
                                {'Key': PRESERVE_REASON_KEY, 'Value': reason}
                            ]
                        )
                        self.tagging_results['resources_tagged'] += 1
                        print(f"    Tagged user: {user['UserName']}")
                except Exception as e:
                    self.tagging_results['resources_failed'] += 1
                    self.tagging_results['errors'].append(f"Failed to tag user {user['UserName']}: {str(e)}")
        
        # Tag IAM policies
        if 'iam_policies' in self.inventory.get('global_resources', {}):
            policies = self.inventory['global_resources']['iam_policies'].get('resources', [])
            for policy in policies:
                try:
                    preserve, reason = self.should_preserve_resource(policy['PolicyName'], 'AWS::IAM::Policy')
                    if preserve:
                        iam.tag_policy(
                            PolicyArn=policy['Arn'],
                            Tags=[
                                {'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE},
                                {'Key': PRESERVE_REASON_KEY, 'Value': reason}
                            ]
                        )
                        self.tagging_results['resources_tagged'] += 1
                        print(f"    Tagged policy: {policy['PolicyName']}")
                except Exception as e:
                    self.tagging_results['resources_failed'] += 1
                    self.tagging_results['errors'].append(f"Failed to tag policy {policy['PolicyName']}: {str(e)}")
    
    def tag_cloudformation_stacks(self, region: str):
        """Tag CloudFormation stacks for preservation"""
        if 'cloudformation_stacks' not in self.inventory['regions'].get(region, {}).get('resources', {}):
            return
            
        print(f"    Tagging CloudFormation stacks in {region}...")
        cfn = self.session.client('cloudformation', region_name=region)
        
        stacks = self.inventory['regions'][region]['resources']['cloudformation_stacks'].get('resources', [])
        for stack in stacks:
            try:
                preserve, reason = self.should_preserve_resource(stack['StackName'])
                if preserve:
                    # CloudFormation uses different tagging API
                    current_tags = cfn.describe_stacks(StackName=stack['StackName'])['Stacks'][0].get('Tags', [])
                    
                    # Add our tags
                    new_tags = current_tags + [
                        {'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE},
                        {'Key': PRESERVE_REASON_KEY, 'Value': reason}
                    ]
                    
                    # Update stack with new tags
                    try:
                        cfn.update_stack(
                            StackName=stack['StackName'],
                            UsePreviousTemplate=True,
                            Tags=new_tags,
                            Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND']
                        )
                        self.tagging_results['resources_tagged'] += 1
                        print(f"      Tagged stack: {stack['StackName']}")
                    except Exception as e:
                        if 'No updates are to be performed' in str(e):
                            # Stack doesn't need updating, just tag it
                            print(f"      Stack {stack['StackName']} already up to date")
                        else:
                            raise
                            
            except Exception as e:
                self.tagging_results['resources_failed'] += 1
                self.tagging_results['errors'].append(f"Failed to tag stack {stack['StackName']}: {str(e)}")
    
    def tag_s3_buckets(self):
        """Tag S3 buckets for preservation"""
        if 's3_buckets' not in self.inventory['regions'].get('us-east-1', {}).get('resources', {}):
            return
            
        print(f"  Tagging S3 buckets...")
        s3 = self.session.client('s3')
        
        buckets = self.inventory['regions']['us-east-1']['resources']['s3_buckets'].get('resources', [])
        for bucket in buckets:
            try:
                preserve, reason = self.should_preserve_resource(bucket['Name'])
                if preserve:
                    # Get current tags
                    try:
                        current_tags = s3.get_bucket_tagging(Bucket=bucket['Name'])['TagSet']
                    except:
                        current_tags = []
                    
                    # Add our tags
                    new_tags = current_tags + [
                        {'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE},
                        {'Key': PRESERVE_REASON_KEY, 'Value': reason}
                    ]
                    
                    # Apply tags
                    s3.put_bucket_tagging(
                        Bucket=bucket['Name'],
                        Tagging={'TagSet': new_tags}
                    )
                    self.tagging_results['resources_tagged'] += 1
                    print(f"    Tagged bucket: {bucket['Name']}")
                    
            except Exception as e:
                self.tagging_results['resources_failed'] += 1
                self.tagging_results['errors'].append(f"Failed to tag bucket {bucket['Name']}: {str(e)}")
    
    def tag_ec2_resources(self, region: str):
        """Tag EC2 resources for preservation"""
        regional_resources = self.inventory['regions'].get(region, {}).get('resources', {})
        if not any(key.startswith('ec2_') or key in ['vpcs', 'security_groups'] for key in regional_resources):
            return
            
        print(f"    Tagging EC2 resources in {region}...")
        ec2 = self.session.client('ec2', region_name=region)
        
        # Collect resource IDs to tag
        resource_ids = []
        
        # VPCs
        if 'vpcs' in regional_resources:
            for vpc in regional_resources['vpcs'].get('resources', []):
                preserve, _ = self.should_preserve_resource(vpc.get('Tags', [{}])[0].get('Value', ''))
                if preserve:
                    resource_ids.append(vpc['VpcId'])
        
        # Security Groups
        if 'security_groups' in regional_resources:
            for sg in regional_resources['security_groups'].get('resources', []):
                preserve, _ = self.should_preserve_resource(sg['GroupName'])
                if preserve:
                    resource_ids.append(sg['GroupId'])
        
        # Tag all collected resources
        if resource_ids:
            try:
                ec2.create_tags(
                    Resources=resource_ids,
                    Tags=[
                        {'Key': PRESERVE_TAG_KEY, 'Value': PRESERVE_TAG_VALUE},
                        {'Key': PRESERVE_REASON_KEY, 'Value': 'Infrastructure resource'}
                    ]
                )
                self.tagging_results['resources_tagged'] += len(resource_ids)
                print(f"      Tagged {len(resource_ids)} EC2 resources")
            except Exception as e:
                self.tagging_results['resources_failed'] += len(resource_ids)
                self.tagging_results['errors'].append(f"Failed to tag EC2 resources in {region}: {str(e)}")
    
    def tag_resources(self):
        """Main tagging execution"""
        print(f"\nTagging resources in account {self.account_id} ({self.profile_name})")
        
        # Tag global resources
        try:
            self.tag_iam_resources()
        except Exception as e:
            print(f"  Error tagging IAM resources: {e}")
        
        try:
            self.tag_s3_buckets()
        except Exception as e:
            print(f"  Error tagging S3 buckets: {e}")
        
        # Tag regional resources
        for region in self.inventory.get('regions', {}):
            try:
                self.tag_cloudformation_stacks(region)
                self.tag_ec2_resources(region)
            except Exception as e:
                print(f"  Error tagging resources in {region}: {e}")
        
        self.tagging_results['end_time'] = datetime.utcnow().isoformat()
        
        # Save results
        output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/tagging/results"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/tagging_{self.account_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.tagging_results, f, indent=2)
        
        print(f"\nTagging complete for account {self.account_id}")
        print(f"  Resources tagged: {self.tagging_results['resources_tagged']}")
        print(f"  Resources failed: {self.tagging_results['resources_failed']}")
        print(f"  Results saved to: {filename}")
        
        return self.tagging_results


def main():
    """Main execution function"""
    print("AWS Tagging Agent Starting...")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    
    # Load consolidated inventory to get account list
    inventory_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/inventory/results"
    consolidated_file = None
    
    # Find the latest consolidated inventory
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
    
    # Tag resources in each account
    for profile, account_data in consolidated['accounts'].items():
        try:
            print(f"\nProcessing {profile}...")
            agent = AWSTaggingAgent(profile, account_data['inventory_file'])
            results = agent.tag_resources()
            all_results[profile] = results
        except Exception as e:
            print(f"Error processing {profile}: {e}")
            all_results[profile] = {'error': str(e)}
    
    # Generate summary report
    summary = {
        'execution_time': datetime.utcnow().isoformat(),
        'accounts_processed': len(all_results),
        'total_tagged': sum(r.get('resources_tagged', 0) for r in all_results.values()),
        'total_failed': sum(r.get('resources_failed', 0) for r in all_results.values()),
        'by_account': {}
    }
    
    for profile, results in all_results.items():
        if 'error' in results:
            summary['by_account'][profile] = {'status': 'error', 'error': results['error']}
        else:
            summary['by_account'][profile] = {
                'status': 'success',
                'tagged': results.get('resources_tagged', 0),
                'failed': results.get('resources_failed', 0),
                'errors': len(results.get('errors', []))
            }
    
    # Save summary
    output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/tagging/results"
    summary_file = f"{output_dir}/tagging_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n\nTagging Agent Complete!")
    print(f"Summary saved to: {summary_file}")
    print(f"Total resources tagged: {summary['total_tagged']}")
    print(f"Total failures: {summary['total_failed']}")


if __name__ == "__main__":
    main()