#!/usr/bin/env python3
"""
Compute Destruction Agent - Destroys ALL compute resources for account closure
"""

import json
import boto3
import concurrent.futures
import time
from datetime import datetime
import os
import sys
from typing import Dict, List, Any

class ComputeDestructionAgent:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.account_id = self.get_account_id()
        self.destruction_log = {
            'account_id': self.account_id,
            'profile_name': profile_name,
            'start_time': datetime.utcnow().isoformat(),
            'agent_type': 'compute_destruction',
            'destroyed': [],
            'failed': [],
            'summary': {
                'ec2_instances': 0, 'lambda_functions': 0, 'rds_instances': 0, 
                'rds_clusters': 0, 'ecs_clusters': 0, 'failed': 0
            }
        }
        
    def get_account_id(self) -> str:
        try:
            sts = self.session.client('sts')
            return sts.get_caller_identity()['Account']
        except Exception as e:
            print(f"Error getting account ID: {e}")
            return "unknown"
    
    def destroy_ec2_instances(self, region: str):
        """Destroy all EC2 instances in a region"""
        print(f"🔥 DESTROYING EC2 INSTANCES in {region}...")
        ec2 = self.session.client('ec2', region_name=region)
        
        try:
            instances = ec2.describe_instances(
                Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'stopping']}]
            )
            
            instance_ids = []
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_ids.append(instance['InstanceId'])
            
            if not instance_ids:
                print(f"  No EC2 instances found in {region}")
                return
                
            print(f"  Found {len(instance_ids)} instances to destroy")
            
            # Disable termination protection for all instances
            for instance_id in instance_ids:
                try:
                    ec2.modify_instance_attribute(
                        InstanceId=instance_id,
                        DisableApiTermination={'Value': False}
                    )
                except:
                    pass  # Instance might not have termination protection
            
            # Terminate all instances
            print(f"  🗑️  Terminating {len(instance_ids)} instances...")
            ec2.terminate_instances(InstanceIds=instance_ids)
            
            for instance_id in instance_ids:
                self.destruction_log['destroyed'].append({
                    'type': 'ec2_instance',
                    'id': instance_id,
                    'region': region,
                    'timestamp': datetime.utcnow().isoformat()
                })
                self.destruction_log['summary']['ec2_instances'] += 1
                print(f"    ✅ TERMINATED: {instance_id}")
                
        except Exception as e:
            print(f"Error destroying EC2 instances in {region}: {e}")
    
    def destroy_lambda_functions(self, region: str):
        """Destroy all Lambda functions in a region"""
        print(f"🔥 DESTROYING LAMBDA FUNCTIONS in {region}...")
        lambda_client = self.session.client('lambda', region_name=region)
        
        try:
            paginator = lambda_client.get_paginator('list_functions')
            functions = []
            for page in paginator.paginate():
                functions.extend(page['Functions'])
            
            if not functions:
                print(f"  No Lambda functions found in {region}")
                return
                
            print(f"  Found {len(functions)} functions to destroy")
            
            for function in functions:
                function_name = function['FunctionName']
                try:
                    print(f"  🗑️  Destroying function: {function_name}")
                    lambda_client.delete_function(FunctionName=function_name)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'lambda_function',
                        'id': function_name,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['lambda_functions'] += 1
                    print(f"    ✅ DESTROYED: {function_name}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {function_name} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'lambda_function',
                        'id': function_name,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
                    
        except Exception as e:
            print(f"Error destroying Lambda functions in {region}: {e}")
    
    def destroy_all_compute(self):
        """Main destruction execution"""
        print(f"🔥🔥🔥 COMPUTE DESTRUCTION AGENT - ACCOUNT {self.account_id} 🔥🔥🔥")
        print("⚠️  WARNING: ALL COMPUTE RESOURCES WILL BE PERMANENTLY DESTROYED!")
        
        # Get all regions
        ec2 = self.session.client('ec2', region_name='us-east-1')
        regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
        
        # Process regions with resources first
        priority_regions = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
        other_regions = [r for r in regions if r not in priority_regions]
        
        all_regions = priority_regions + other_regions
        
        for region in all_regions:
            try:
                print(f"\n🌍 Processing region: {region}")
                self.destroy_lambda_functions(region)
                self.destroy_ec2_instances(region)
            except Exception as e:
                print(f"Error processing region {region}: {e}")
        
        self.destruction_log['end_time'] = datetime.utcnow().isoformat()
        
        # Save results
        output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure/results"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/compute_destruction_{self.account_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.destruction_log, f, indent=2)
        
        print(f"\n🔥 COMPUTE DESTRUCTION COMPLETE!")
        print(f"  EC2 Instances destroyed: {self.destruction_log['summary']['ec2_instances']}")
        print(f"  Lambda Functions destroyed: {self.destruction_log['summary']['lambda_functions']}")
        print(f"  Failed: {self.destruction_log['summary']['failed']}")
        print(f"  Results saved to: {filename}")
        
        return self.destruction_log


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 compute_destruction_agent.py <profile_name>")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    print(f"🔥 Starting Compute Destruction Agent for {profile_name}")
    
    agent = ComputeDestructionAgent(profile_name)
    agent.destroy_all_compute()


if __name__ == "__main__":
    main()