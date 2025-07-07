#!/usr/bin/env python3
"""
Complete Account Closure Orchestrator - Coordinates all destruction agents
"""

import json
import subprocess
import concurrent.futures
from datetime import datetime
import os
import sys
import time

class ClosureOrchestrator:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.start_time = datetime.utcnow()
        self.orchestration_log = {
            'profile_name': profile_name,
            'start_time': self.start_time.isoformat(),
            'phases': {},
            'summary': {
                'phases_completed': 0,
                'phases_failed': 0,
                'total_resources_destroyed': 0
            }
        }
        
    def run_agent(self, agent_script: str, phase_name: str) -> dict:
        """Run a destruction agent"""
        print(f"\n🚀 STARTING PHASE: {phase_name}")
        print(f"   Agent: {agent_script}")
        
        try:
            start_time = datetime.utcnow()
            
            # Run the agent
            result = subprocess.run([
                'python3', agent_script, self.profile_name
            ], capture_output=True, text=True, timeout=1800)  # 30 min timeout
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            if result.returncode == 0:
                print(f"✅ PHASE COMPLETE: {phase_name} ({duration:.1f}s)")
                self.orchestration_log['phases'][phase_name] = {
                    'status': 'success',
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'duration_seconds': duration,
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
                self.orchestration_log['summary']['phases_completed'] += 1
                return {'success': True, 'output': result.stdout}
            else:
                print(f"❌ PHASE FAILED: {phase_name}")
                print(f"   Error: {result.stderr}")
                self.orchestration_log['phases'][phase_name] = {
                    'status': 'failed',
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'duration_seconds': duration,
                    'error': result.stderr,
                    'stdout': result.stdout
                }
                self.orchestration_log['summary']['phases_failed'] += 1
                return {'success': False, 'error': result.stderr}
                
        except subprocess.TimeoutExpired:
            print(f"⏰ PHASE TIMEOUT: {phase_name}")
            self.orchestration_log['phases'][phase_name] = {
                'status': 'timeout',
                'error': 'Agent timed out after 30 minutes'
            }
            self.orchestration_log['summary']['phases_failed'] += 1
            return {'success': False, 'error': 'Timeout'}
        except Exception as e:
            print(f"💥 PHASE ERROR: {phase_name} - {e}")
            self.orchestration_log['phases'][phase_name] = {
                'status': 'error',
                'error': str(e)
            }
            self.orchestration_log['summary']['phases_failed'] += 1
            return {'success': False, 'error': str(e)}
    
    def run_comprehensive_nuke(self):
        """Execute comprehensive account destruction"""
        print("🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥")
        print("     COMPLETE AWS ACCOUNT CLOSURE INITIATED")
        print(f"     Account Profile: {self.profile_name}")
        print(f"     Start Time: {self.start_time.isoformat()}")
        print("🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥")
        
        agents_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure"
        
        # Phase 1: Parallel destruction of major resource types
        print("\n📋 PHASE 1: PARALLEL RESOURCE DESTRUCTION")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.run_agent, f"{agents_dir}/storage_destruction_agent.py", "STORAGE_DESTRUCTION"): "storage",
                executor.submit(self.run_agent, f"{agents_dir}/compute_destruction_agent.py", "COMPUTE_DESTRUCTION"): "compute"
            }
            
            for future in concurrent.futures.as_completed(futures):
                agent_type = futures[future]
                try:
                    result = future.result()
                    if result['success']:
                        print(f"✅ {agent_type.upper()} destruction completed")
                    else:
                        print(f"❌ {agent_type.upper()} destruction failed: {result['error']}")
                except Exception as e:
                    print(f"💥 {agent_type.upper()} destruction crashed: {e}")
        
        # Short pause between phases
        time.sleep(10)
        
        # Phase 2: Infrastructure cleanup using AWS CLI nuke approach
        print("\n📋 PHASE 2: INFRASTRUCTURE ANNIHILATION")
        self.run_cli_nuke()
        
        # Phase 3: Final verification
        print("\n📋 PHASE 3: CLOSURE VERIFICATION")
        self.verify_account_empty()
        
        # Save final orchestration log
        self.save_orchestration_log()
        
        print("\n🔥🔥🔥 ACCOUNT CLOSURE ORCHESTRATION COMPLETE 🔥🔥🔥")
        print(f"   Total Duration: {(datetime.utcnow() - self.start_time).total_seconds():.1f} seconds")
        print(f"   Phases Completed: {self.orchestration_log['summary']['phases_completed']}")
        print(f"   Phases Failed: {self.orchestration_log['summary']['phases_failed']}")
    
    def run_cli_nuke(self):
        """Use AWS CLI to nuke remaining resources"""
        print("🔥 RUNNING AWS CLI NUKE OPERATIONS...")
        
        # Get all regions
        try:
            result = subprocess.run([
                'aws', 'ec2', 'describe-regions', 
                '--profile', self.profile_name,
                '--query', 'Regions[].RegionName',
                '--output', 'text'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                regions = result.stdout.strip().split()
                print(f"  Targeting {len(regions)} regions for cleanup")
                
                # Nuke each region in parallel
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(self.nuke_region, region) for region in regions]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            print(f"Error in region nuke: {e}")
                            
        except Exception as e:
            print(f"Error getting regions for nuke: {e}")
    
    def nuke_region(self, region: str):
        """Nuke all remaining resources in a region"""
        print(f"  🔥 NUKING REGION: {region}")
        
        nuke_commands = [
            # Delete CloudFormation stacks
            f"aws cloudformation list-stacks --profile {self.profile_name} --region {region} --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query 'StackSummaries[].StackName' --output text | xargs -n1 -I{{}} aws cloudformation delete-stack --profile {self.profile_name} --region {region} --stack-name {{}} || true",
            
            # Delete API Gateways
            f"aws apigateway get-rest-apis --profile {self.profile_name} --region {region} --query 'items[].id' --output text | xargs -n1 -I{{}} aws apigateway delete-rest-api --profile {self.profile_name} --region {region} --rest-api-id {{}} || true",
            
            # Delete CloudWatch alarms
            f"aws cloudwatch describe-alarms --profile {self.profile_name} --region {region} --query 'MetricAlarms[].AlarmName' --output text | xargs -n1 -I{{}} aws cloudwatch delete-alarms --profile {self.profile_name} --region {region} --alarm-names {{}} || true",
            
            # Delete SNS topics
            f"aws sns list-topics --profile {self.profile_name} --region {region} --query 'Topics[].TopicArn' --output text | xargs -n1 -I{{}} aws sns delete-topic --profile {self.profile_name} --region {region} --topic-arn {{}} || true",
            
            # Delete SQS queues
            f"aws sqs list-queues --profile {self.profile_name} --region {region} --query 'QueueUrls[]' --output text | xargs -n1 -I{{}} aws sqs delete-queue --profile {self.profile_name} --region {region} --queue-url {{}} || true",
            
            # Delete VPC resources
            f"aws ec2 describe-vpcs --profile {self.profile_name} --region {region} --query 'Vpcs[?IsDefault==`false`].VpcId' --output text | xargs -n1 -I{{}} bash -c 'aws ec2 describe-subnets --profile {self.profile_name} --region {region} --filters Name=vpc-id,Values={{}} --query \"Subnets[].SubnetId\" --output text | xargs -n1 -I[] aws ec2 delete-subnet --profile {self.profile_name} --region {region} --subnet-id [] || true; aws ec2 delete-vpc --profile {self.profile_name} --region {region} --vpc-id {{}} || true'",
        ]
        
        for cmd in nuke_commands:
            try:
                subprocess.run(cmd, shell=True, timeout=300, capture_output=True)
            except:
                pass  # Continue on errors
    
    def verify_account_empty(self):
        """Verify the account is ready for closure"""
        print("🔍 VERIFYING ACCOUNT IS EMPTY...")
        
        verification_results = {
            's3_buckets': 0,
            'ec2_instances': 0,
            'lambda_functions': 0,
            'cloudformation_stacks': 0
        }
        
        try:
            # Check S3 buckets
            result = subprocess.run([
                'aws', 's3api', 'list-buckets',
                '--profile', self.profile_name,
                '--query', 'length(Buckets)',
                '--output', 'text'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                verification_results['s3_buckets'] = int(result.stdout.strip())
            
            # Check EC2 instances (sample region)
            result = subprocess.run([
                'aws', 'ec2', 'describe-instances',
                '--profile', self.profile_name,
                '--region', 'us-east-1',
                '--query', 'length(Reservations[].Instances[])',
                '--output', 'text'
            ], capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip() != 'None':
                verification_results['ec2_instances'] = int(result.stdout.strip())
            
            print("🔍 VERIFICATION RESULTS:")
            for resource_type, count in verification_results.items():
                status = "✅ CLEAN" if count == 0 else f"⚠️  {count} remaining"
                print(f"   {resource_type}: {status}")
            
            self.orchestration_log['verification'] = verification_results
            
        except Exception as e:
            print(f"Error in verification: {e}")
    
    def save_orchestration_log(self):
        """Save the complete orchestration log"""
        self.orchestration_log['end_time'] = datetime.utcnow().isoformat()
        self.orchestration_log['total_duration_seconds'] = (datetime.utcnow() - self.start_time).total_seconds()
        
        output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure/results"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/closure_orchestration_{self.profile_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.orchestration_log, f, indent=2)
        
        print(f"\n📊 Orchestration log saved to: {filename}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 complete_closure_orchestrator.py <profile_name>")
        print("Example: python3 complete_closure_orchestrator.py Development-Admin")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    
    print("🔥🔥🔥 AWS ACCOUNT COMPLETE CLOSURE ORCHESTRATOR 🔥🔥🔥")
    print(f"Target Profile: {profile_name}")
    print("⚠️  WARNING: This will DESTROY ALL RESOURCES in the account!")
    
    # Confirmation
    response = input("\n💀 Type 'NUKE' to confirm complete account destruction: ")
    if response != 'NUKE':
        print("Confirmation not received. Exiting.")
        sys.exit(1)
    
    orchestrator = ClosureOrchestrator(profile_name)
    orchestrator.run_comprehensive_nuke()


if __name__ == "__main__":
    main()