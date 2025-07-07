#!/usr/bin/env python3
"""
Infrastructure Destruction Agent - Destroys ALL infrastructure for account closure
"""

import json
import boto3
import concurrent.futures
import time
from datetime import datetime
import os
import sys
from typing import Dict, List, Any

class InfrastructureDestructionAgent:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.account_id = self.get_account_id()
        self.destruction_log = {
            'account_id': self.account_id,
            'profile_name': profile_name,
            'start_time': datetime.utcnow().isoformat(),
            'agent_type': 'infrastructure_destruction',
            'destroyed': [],
            'failed': [],
            'summary': {
                'cloudformation_stacks': 0, 'vpcs': 0, 'security_groups': 0,
                'internet_gateways': 0, 'nat_gateways': 0, 'failed': 0
            }
        }
        
    def get_account_id(self) -> str:
        try:
            sts = self.session.client('sts')
            return sts.get_caller_identity()['Account']
        except Exception as e:
            print(f"Error getting account ID: {e}")
            return "unknown"
    
    def destroy_cloudformation_stacks(self, region: str):
        """Destroy ALL CloudFormation stacks in a region"""
        print(f"🔥 DESTROYING CLOUDFORMATION STACKS in {region}...")
        cfn = self.session.client('cloudformation', region_name=region)
        
        try:
            # Get all stacks (including Control Tower ones)
            stacks = []
            paginator = cfn.get_paginator('list_stacks')
            for page in paginator.paginate(StackStatusFilter=[
                'CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE',
                'ROLLBACK_COMPLETE', 'IMPORT_COMPLETE', 'IMPORT_ROLLBACK_COMPLETE'
            ]):
                stacks.extend(page['StackSummaries'])
            
            if not stacks:
                print(f"  No CloudFormation stacks found in {region}")
                return
                
            print(f"  Found {len(stacks)} stacks to destroy")
            
            # Sort stacks - destroy dependent stacks first, Control Tower last
            def stack_priority(stack):
                name = stack['StackName'].lower()
                if 'controltower' in name or 'aws-landing-zone' in name:
                    return 3  # Delete Control Tower stacks last
                elif name.startswith('stackset-'):
                    return 2  # Delete StackSets second to last
                else:
                    return 1  # Delete application stacks first
            
            sorted_stacks = sorted(stacks, key=stack_priority)
            
            for stack in sorted_stacks:
                stack_name = stack['StackName']
                try:
                    print(f"  🗑️  Destroying stack: {stack_name}")
                    
                    # Disable termination protection if enabled
                    try:
                        stack_details = cfn.describe_stacks(StackName=stack_name)['Stacks'][0]
                        if stack_details.get('EnableTerminationProtection', False):
                            cfn.update_termination_protection(
                                StackName=stack_name,
                                EnableTerminationProtection=False
                            )
                    except:
                        pass
                    
                    # Delete the stack
                    cfn.delete_stack(StackName=stack_name)
                    
                    # Wait for deletion to start
                    time.sleep(2)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'cloudformation_stack',
                        'id': stack_name,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['cloudformation_stacks'] += 1
                    print(f"    ✅ DELETING: {stack_name} (deletion in progress)")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {stack_name} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'cloudformation_stack',
                        'id': stack_name,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
                    
        except Exception as e:
            print(f"Error destroying CloudFormation stacks in {region}: {e}")
    
    def destroy_networking(self, region: str):
        """Destroy networking resources in a region"""
        print(f"🔥 DESTROYING NETWORKING in {region}...")
        ec2 = self.session.client('ec2', region_name=region)
        
        try:
            # Destroy NAT Gateways first
            nat_gateways = ec2.describe_nat_gateways(
                Filters=[{'Name': 'state', 'Values': ['available']}]
            )['NatGateways']
            
            for nat in nat_gateways:
                nat_id = nat['NatGatewayId']
                try:
                    print(f"  🗑️  Destroying NAT Gateway: {nat_id}")
                    ec2.delete_nat_gateway(NatGatewayId=nat_id)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'nat_gateway',
                        'id': nat_id,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['nat_gateways'] += 1
                    print(f"    ✅ DESTROYED: {nat_id}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {nat_id} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'nat_gateway',
                        'id': nat_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
            
            # Destroy Internet Gateways
            igws = ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.state', 'Values': ['available']}]
            )['InternetGateways']
            
            for igw in igws:
                igw_id = igw['InternetGatewayId']
                try:
                    print(f"  🗑️  Destroying Internet Gateway: {igw_id}")
                    
                    # Detach from VPCs first
                    for attachment in igw.get('Attachments', []):
                        vpc_id = attachment['VpcId']
                        ec2.detach_internet_gateway(
                            InternetGatewayId=igw_id,
                            VpcId=vpc_id
                        )
                    
                    # Delete the IGW
                    ec2.delete_internet_gateway(InternetGatewayId=igw_id)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'internet_gateway',
                        'id': igw_id,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['internet_gateways'] += 1
                    print(f"    ✅ DESTROYED: {igw_id}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {igw_id} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'internet_gateway',
                        'id': igw_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
            
            # Destroy Security Groups (except default)
            security_groups = ec2.describe_security_groups()['SecurityGroups']
            custom_sgs = [sg for sg in security_groups if sg['GroupName'] != 'default']
            
            for sg in custom_sgs:
                sg_id = sg['GroupId']
                try:
                    print(f"  🗑️  Destroying Security Group: {sg_id}")
                    ec2.delete_security_group(GroupId=sg_id)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'security_group',
                        'id': sg_id,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['security_groups'] += 1
                    print(f"    ✅ DESTROYED: {sg_id}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {sg_id} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'security_group',
                        'id': sg_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
            
            # Destroy VPCs (except default)
            vpcs = ec2.describe_vpcs()['Vpcs']
            custom_vpcs = [vpc for vpc in vpcs if not vpc['IsDefault']]
            
            for vpc in custom_vpcs:
                vpc_id = vpc['VpcId']
                try:
                    print(f"  🗑️  Destroying VPC: {vpc_id}")
                    
                    # Delete subnets first
                    subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Subnets']
                    for subnet in subnets:
                        ec2.delete_subnet(SubnetId=subnet['SubnetId'])
                    
                    # Delete route tables (except main)
                    route_tables = ec2.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['RouteTables']
                    for rt in route_tables:
                        if not any(assoc.get('Main', False) for assoc in rt.get('Associations', [])):
                            ec2.delete_route_table(RouteTableId=rt['RouteTableId'])
                    
                    # Delete the VPC
                    ec2.delete_vpc(VpcId=vpc_id)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'vpc',
                        'id': vpc_id,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['vpcs'] += 1
                    print(f"    ✅ DESTROYED: {vpc_id}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {vpc_id} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'vpc',
                        'id': vpc_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
                    
        except Exception as e:
            print(f"Error destroying networking in {region}: {e}")
    
    def destroy_all_infrastructure(self):
        """Main destruction execution"""
        print(f"🔥🔥🔥 INFRASTRUCTURE DESTRUCTION AGENT - ACCOUNT {self.account_id} 🔥🔥🔥")
        print("⚠️  WARNING: ALL INFRASTRUCTURE WILL BE PERMANENTLY DESTROYED!")
        
        # Get all regions
        ec2 = self.session.client('ec2', region_name='us-east-1')
        regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
        
        # Process CloudFormation stacks first in priority regions
        priority_regions = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
        other_regions = [r for r in regions if r not in priority_regions]
        
        all_regions = priority_regions + other_regions
        
        # Phase 1: Delete CloudFormation stacks
        print("\n🔥 PHASE 1: DESTROYING CLOUDFORMATION STACKS")
        for region in all_regions:
            try:
                print(f"\n🌍 Processing CloudFormation in: {region}")
                self.destroy_cloudformation_stacks(region)
            except Exception as e:
                print(f"Error processing CloudFormation in {region}: {e}")
        
        # Wait for stack deletions to complete
        print("\n⏳ Waiting for CloudFormation deletions to complete...")
        time.sleep(30)
        
        # Phase 2: Clean up networking
        print("\n🔥 PHASE 2: DESTROYING NETWORKING")
        for region in all_regions:
            try:
                print(f"\n🌍 Processing networking in: {region}")
                self.destroy_networking(region)
            except Exception as e:
                print(f"Error processing networking in {region}: {e}")
        
        self.destruction_log['end_time'] = datetime.utcnow().isoformat()
        
        # Save results
        output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure/results"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/infrastructure_destruction_{self.account_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.destruction_log, f, indent=2)
        
        print(f"\n🔥 INFRASTRUCTURE DESTRUCTION COMPLETE!")
        print(f"  CloudFormation Stacks: {self.destruction_log['summary']['cloudformation_stacks']}")
        print(f"  VPCs destroyed: {self.destruction_log['summary']['vpcs']}")
        print(f"  Security Groups: {self.destruction_log['summary']['security_groups']}")
        print(f"  Internet Gateways: {self.destruction_log['summary']['internet_gateways']}")
        print(f"  NAT Gateways: {self.destruction_log['summary']['nat_gateways']}")
        print(f"  Failed: {self.destruction_log['summary']['failed']}")
        print(f"  Results saved to: {filename}")
        
        return self.destruction_log


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 infrastructure_destruction_agent.py <profile_name>")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    print(f"🔥 Starting Infrastructure Destruction Agent for {profile_name}")
    
    agent = InfrastructureDestructionAgent(profile_name)
    agent.destroy_all_infrastructure()


if __name__ == "__main__":
    main()