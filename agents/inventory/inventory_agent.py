#!/usr/bin/env python3
"""
AWS Inventory Agent - Comprehensive resource discovery across all accounts and regions
"""

import json
import boto3
import concurrent.futures
from datetime import datetime
import os
import sys
from typing import Dict, List, Any, Set

PRESERVE_RESOURCE_TYPES = {
    'AWS::Organizations::Account',
    'AWS::Organizations::OrganizationalUnit',
    'AWS::Organizations::Root',
    'AWS::ControlTower::LandingZone',
    'AWS::IAM::Role',
    'AWS::IAM::User',
    'AWS::IAM::Policy',
    'AWS::IAM::ManagedPolicy',
    'AWS::Route53::HostedZone',
    'AWS::Route53::Domain',
    'AWS::Budgets::Budget',
    'AWS::Support::SupportPlan',
    'AWS::SavingsPlans::SavingsPlan',
}

PRESERVE_TAG = "decom:preserve"

ALL_REGIONS = [
    'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
    'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1',
    'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1', 'ap-northeast-2',
    'ap-south-1', 'ca-central-1', 'sa-east-1', 'eu-north-1',
    'eu-south-1', 'ap-east-1', 'me-south-1', 'af-south-1'
]

SERVICE_TO_RESOURCE_TYPES = {
    'ec2': ['instances', 'volumes', 'snapshots', 'security-groups', 'vpcs', 'subnets', 'route-tables', 'internet-gateways', 'nat-gateways', 'elastic-ips'],
    's3': ['buckets'],
    'rds': ['db-instances', 'db-clusters', 'db-snapshots'],
    'lambda': ['functions'],
    'dynamodb': ['tables'],
    'ecs': ['clusters', 'services', 'task-definitions'],
    'eks': ['clusters'],
    'cloudformation': ['stacks'],
    'elasticbeanstalk': ['applications', 'environments'],
    'sqs': ['queues'],
    'sns': ['topics'],
    'kinesis': ['streams'],
    'apigateway': ['rest-apis', 'http-apis'],
    'cloudfront': ['distributions'],
    'elasticache': ['clusters'],
    'iam': ['roles', 'users', 'policies', 'groups'],
    'route53': ['hosted-zones', 'domains'],
    'acm': ['certificates'],
    'waf': ['web-acls'],
    'cloudwatch': ['alarms', 'dashboards'],
    'logs': ['log-groups'],
    'events': ['rules'],
    'backup': ['backup-plans', 'backup-vaults'],
    'secretsmanager': ['secrets'],
    'ssm': ['parameters'],
    'organizations': ['accounts', 'organizational-units'],
    'controltower': ['landing-zones'],
    'budgets': ['budgets'],
    'savingsplans': ['savings-plans'],
}

class AWSInventoryAgent:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.account_id = self.get_account_id()
        self.inventory = {
            'account_id': self.account_id,
            'profile_name': profile_name,
            'scan_time': datetime.utcnow().isoformat(),
            'regions': {},
            'global_resources': {},
            'summary': {
                'total_resources': 0,
                'resources_to_preserve': 0,
                'resources_to_delete': 0,
                'by_service': {},
                'by_region': {}
            }
        }
        
    def get_account_id(self) -> str:
        try:
            sts = self.session.client('sts')
            return sts.get_caller_identity()['Account']
        except Exception as e:
            print(f"Error getting account ID for profile {self.profile_name}: {e}")
            return "unknown"
    
    def scan_global_resources(self):
        """Scan global resources (IAM, Route53, Organizations, etc.)"""
        print(f"  Scanning global resources for account {self.account_id}")
        
        # IAM Resources
        try:
            iam = self.session.client('iam')
            
            # Scan IAM roles
            paginator = iam.get_paginator('list_roles')
            roles = []
            for page in paginator.paginate():
                roles.extend(page['Roles'])
            self.inventory['global_resources']['iam_roles'] = {
                'count': len(roles),
                'preserve': True,
                'resources': [{'RoleName': r['RoleName'], 'Arn': r['Arn']} for r in roles]
            }
            
            # Scan IAM users
            paginator = iam.get_paginator('list_users')
            users = []
            for page in paginator.paginate():
                users.extend(page['Users'])
            self.inventory['global_resources']['iam_users'] = {
                'count': len(users),
                'preserve': True,
                'resources': [{'UserName': u['UserName'], 'Arn': u['Arn']} for u in users]
            }
            
            # Scan IAM policies
            paginator = iam.get_paginator('list_policies')
            policies = []
            for page in paginator.paginate(Scope='Local'):
                policies.extend(page['Policies'])
            self.inventory['global_resources']['iam_policies'] = {
                'count': len(policies),
                'preserve': True,
                'resources': [{'PolicyName': p['PolicyName'], 'Arn': p['Arn']} for p in policies]
            }
        except Exception as e:
            print(f"    Error scanning IAM: {e}")
        
        # Route53 Resources
        try:
            route53 = self.session.client('route53')
            
            # Hosted zones
            zones = route53.list_hosted_zones()['HostedZones']
            modulair_zones = [z for z in zones if 'modulairhr.com' in z['Name']]
            self.inventory['global_resources']['route53_zones'] = {
                'count': len(zones),
                'preserve_count': len(modulair_zones),
                'resources': zones,
                'to_preserve': modulair_zones
            }
            
            # Domains (if using Route53 domain registration)
            try:
                route53domains = self.session.client('route53domains', region_name='us-east-1')
                domains = route53domains.list_domains()['Domains']
                self.inventory['global_resources']['route53_domains'] = {
                    'count': len(domains),
                    'preserve': True,
                    'resources': domains
                }
            except:
                pass
                
        except Exception as e:
            print(f"    Error scanning Route53: {e}")
        
        # Organizations (if this is the management account)
        if self.profile_name == 'Management-Admin':
            try:
                org = self.session.client('organizations')
                
                # List accounts
                accounts = []
                paginator = org.get_paginator('list_accounts')
                for page in paginator.paginate():
                    accounts.extend(page['Accounts'])
                self.inventory['global_resources']['organization_accounts'] = {
                    'count': len(accounts),
                    'preserve': True,
                    'resources': accounts
                }
                
                # List OUs
                ous = []
                roots = org.list_roots()['Roots']
                for root in roots:
                    ous.extend(self._list_ous_recursive(org, root['Id']))
                self.inventory['global_resources']['organizational_units'] = {
                    'count': len(ous),
                    'preserve': True,
                    'resources': ous
                }
                
            except Exception as e:
                print(f"    Error scanning Organizations: {e}")
    
    def _list_ous_recursive(self, org_client, parent_id):
        """Recursively list all OUs"""
        ous = []
        try:
            paginator = org_client.get_paginator('list_organizational_units_for_parent')
            for page in paginator.paginate(ParentId=parent_id):
                for ou in page['OrganizationalUnits']:
                    ous.append(ou)
                    ous.extend(self._list_ous_recursive(org_client, ou['Id']))
        except:
            pass
        return ous
    
    def scan_regional_resources(self, region: str):
        """Scan resources in a specific region"""
        print(f"  Scanning region {region}")
        regional_inventory = {
            'scan_time': datetime.utcnow().isoformat(),
            'resources': {},
            'summary': {
                'total': 0,
                'to_preserve': 0,
                'to_delete': 0
            }
        }
        
        # EC2 Resources
        try:
            ec2 = self.session.client('ec2', region_name=region)
            
            # Instances
            instances = ec2.describe_instances()
            instance_count = sum(len(r['Instances']) for r in instances['Reservations'])
            if instance_count > 0:
                regional_inventory['resources']['ec2_instances'] = {
                    'count': instance_count,
                    'resources': instances['Reservations']
                }
            
            # VPCs
            vpcs = ec2.describe_vpcs()['Vpcs']
            if vpcs:
                regional_inventory['resources']['vpcs'] = {
                    'count': len(vpcs),
                    'resources': vpcs
                }
            
            # Security Groups
            sgs = ec2.describe_security_groups()['SecurityGroups']
            if sgs:
                regional_inventory['resources']['security_groups'] = {
                    'count': len(sgs),
                    'resources': [{'GroupId': sg['GroupId'], 'GroupName': sg['GroupName']} for sg in sgs]
                }
                
        except Exception as e:
            print(f"    Error scanning EC2 in {region}: {e}")
        
        # S3 Buckets (only in us-east-1)
        if region == 'us-east-1':
            try:
                s3 = self.session.client('s3')
                buckets = s3.list_buckets()['Buckets']
                if buckets:
                    regional_inventory['resources']['s3_buckets'] = {
                        'count': len(buckets),
                        'resources': [{'Name': b['Name'], 'CreationDate': b['CreationDate'].isoformat()} for b in buckets]
                    }
            except Exception as e:
                print(f"    Error scanning S3: {e}")
        
        # Lambda Functions
        try:
            lambda_client = self.session.client('lambda', region_name=region)
            functions = []
            paginator = lambda_client.get_paginator('list_functions')
            for page in paginator.paginate():
                functions.extend(page['Functions'])
            if functions:
                regional_inventory['resources']['lambda_functions'] = {
                    'count': len(functions),
                    'resources': [{'FunctionName': f['FunctionName'], 'Runtime': f.get('Runtime', 'N/A')} for f in functions]
                }
        except Exception as e:
            print(f"    Error scanning Lambda in {region}: {e}")
        
        # RDS Instances
        try:
            rds = self.session.client('rds', region_name=region)
            
            # DB Instances
            db_instances = rds.describe_db_instances()['DBInstances']
            if db_instances:
                regional_inventory['resources']['rds_instances'] = {
                    'count': len(db_instances),
                    'resources': [{'DBInstanceIdentifier': db['DBInstanceIdentifier'], 'Engine': db['Engine']} for db in db_instances]
                }
            
            # DB Clusters
            db_clusters = rds.describe_db_clusters()['DBClusters']
            if db_clusters:
                regional_inventory['resources']['rds_clusters'] = {
                    'count': len(db_clusters),
                    'resources': [{'DBClusterIdentifier': db['DBClusterIdentifier'], 'Engine': db['Engine']} for db in db_clusters]
                }
                
        except Exception as e:
            print(f"    Error scanning RDS in {region}: {e}")
        
        # CloudFormation Stacks
        try:
            cfn = self.session.client('cloudformation', region_name=region)
            stacks = []
            paginator = cfn.get_paginator('list_stacks')
            for page in paginator.paginate(StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE']):
                stacks.extend(page['StackSummaries'])
            
            # Check for Control Tower stacks
            ct_stacks = [s for s in stacks if 'ControlTower' in s['StackName'] or 'AWS-Landing-Zone' in s['StackName']]
            
            if stacks:
                regional_inventory['resources']['cloudformation_stacks'] = {
                    'count': len(stacks),
                    'control_tower_stacks': len(ct_stacks),
                    'resources': [{'StackName': s['StackName'], 'Status': s['StackStatus']} for s in stacks],
                    'to_preserve': ct_stacks
                }
                
        except Exception as e:
            print(f"    Error scanning CloudFormation in {region}: {e}")
        
        # Calculate summary
        for service, data in regional_inventory['resources'].items():
            regional_inventory['summary']['total'] += data.get('count', 0)
            regional_inventory['summary']['to_preserve'] += data.get('control_tower_stacks', 0)
        
        regional_inventory['summary']['to_delete'] = regional_inventory['summary']['total'] - regional_inventory['summary']['to_preserve']
        
        return regional_inventory
    
    def scan_account(self):
        """Scan all resources in the account"""
        print(f"\nScanning account {self.account_id} ({self.profile_name})")
        
        # Scan global resources
        self.scan_global_resources()
        
        # Scan each region in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_region = {executor.submit(self.scan_regional_resources, region): region for region in ALL_REGIONS}
            
            for future in concurrent.futures.as_completed(future_to_region):
                region = future_to_region[future]
                try:
                    regional_data = future.result()
                    if regional_data['resources']:  # Only store if resources found
                        self.inventory['regions'][region] = regional_data
                        self.inventory['summary']['by_region'][region] = regional_data['summary']
                except Exception as e:
                    print(f"  Error scanning region {region}: {e}")
        
        # Calculate totals
        self._calculate_summary()
        
        return self.inventory
    
    def _calculate_summary(self):
        """Calculate summary statistics"""
        total = 0
        preserve = 0
        
        # Count global resources
        for resource_type, data in self.inventory['global_resources'].items():
            count = data.get('count', 0)
            total += count
            if data.get('preserve', False):
                preserve += count
            else:
                preserve += data.get('preserve_count', 0)
        
        # Count regional resources
        for region, regional_data in self.inventory['regions'].items():
            total += regional_data['summary']['total']
            preserve += regional_data['summary']['to_preserve']
        
        self.inventory['summary']['total_resources'] = total
        self.inventory['summary']['resources_to_preserve'] = preserve
        self.inventory['summary']['resources_to_delete'] = total - preserve
    
    def save_inventory(self, output_dir: str):
        """Save inventory to file"""
        filename = f"{output_dir}/inventory_{self.account_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(output_dir, exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(self.inventory, f, indent=2, default=str)
        
        print(f"  Inventory saved to {filename}")
        return filename


def main():
    """Main execution function"""
    print("AWS Inventory Agent Starting...")
    print(f"Scan started at: {datetime.utcnow().isoformat()}")
    
    # Get all profiles
    profiles = [
        'Management-Admin',
        'LogArchive-Admin',
        'Audit-Admin',
        'Network-Admin',
        'SharedServices-Admin',
        'Development-Admin',
        'Staging-Admin',
        'Production-Admin',
        'JWModulairHR-Admin'
    ]
    
    all_inventories = {}
    output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/inventory/results"
    
    # Scan each account
    for profile in profiles:
        try:
            agent = AWSInventoryAgent(profile)
            inventory = agent.scan_account()
            filename = agent.save_inventory(output_dir)
            all_inventories[profile] = {
                'inventory': inventory,
                'filename': filename
            }
        except Exception as e:
            print(f"Error scanning profile {profile}: {e}")
    
    # Generate consolidated report
    consolidated_report = {
        'scan_completed': datetime.utcnow().isoformat(),
        'accounts_scanned': len(all_inventories),
        'total_resources_found': sum(inv['inventory']['summary']['total_resources'] for inv in all_inventories.values()),
        'total_to_preserve': sum(inv['inventory']['summary']['resources_to_preserve'] for inv in all_inventories.values()),
        'total_to_delete': sum(inv['inventory']['summary']['resources_to_delete'] for inv in all_inventories.values()),
        'accounts': {}
    }
    
    for profile, data in all_inventories.items():
        consolidated_report['accounts'][profile] = {
            'account_id': data['inventory']['account_id'],
            'total_resources': data['inventory']['summary']['total_resources'],
            'to_preserve': data['inventory']['summary']['resources_to_preserve'],
            'to_delete': data['inventory']['summary']['resources_to_delete'],
            'inventory_file': data['filename']
        }
    
    # Save consolidated report
    report_file = f"{output_dir}/consolidated_inventory_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(consolidated_report, f, indent=2)
    
    print(f"\nInventory scan completed!")
    print(f"Consolidated report saved to: {report_file}")
    print(f"\nSummary:")
    print(f"  Total accounts scanned: {consolidated_report['accounts_scanned']}")
    print(f"  Total resources found: {consolidated_report['total_resources_found']}")
    print(f"  Resources to preserve: {consolidated_report['total_to_preserve']}")
    print(f"  Resources to delete: {consolidated_report['total_to_delete']}")


if __name__ == "__main__":
    main()