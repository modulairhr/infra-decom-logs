#!/usr/bin/env python3
"""
Account Closure Orchestrator - Coordinates all destruction agents for complete account closure
"""

import json
import subprocess
import time
import concurrent.futures
from datetime import datetime
import os
import sys

class AccountClosureOrchestrator:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.agents_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure"
        self.results_dir = f"{self.agents_dir}/results"
        self.closure_log = {
            'profile_name': profile_name,
            'start_time': datetime.utcnow().isoformat(),
            'phases': {},
            'summary': {
                'total_resources_destroyed': 0,
                'total_failures': 0,
                'completion_status': 'in_progress'
            }
        }
        
    def run_agent(self, agent_script: str, agent_name: str) -> dict:
        """Run a destruction agent and return results"""
        print(f"\n🚀 LAUNCHING {agent_name.upper()} AGENT")
        print("=" * 60)
        
        start_time = datetime.utcnow()
        script_path = f"{self.agents_dir}/{agent_script}"
        
        try:
            # Make script executable
            subprocess.run(['chmod', '+x', script_path], check=True)
            
            # Run the agent
            result = subprocess.run(
                ['python3', script_path, self.profile_name],
                cwd=self.agents_dir,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            # Parse output for key metrics
            output_lines = result.stdout.split('\n')
            destroyed_count = 0
            failed_count = 0
            
            for line in output_lines:
                if 'destroyed:' in line.lower() or 'complete!' in line.lower():
                    try:
                        # Extract numbers from summary lines
                        import re
                        numbers = re.findall(r'\d+', line)
                        if numbers:
                            destroyed_count += int(numbers[0])
                    except:
                        pass
                elif 'failed:' in line.lower():
                    try:
                        numbers = re.findall(r'\d+', line)
                        if numbers:
                            failed_count += int(numbers[0])
                    except:
                        pass
            
            phase_result = {
                'agent': agent_name,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'status': 'success' if result.returncode == 0 else 'failed',
                'return_code': result.returncode,
                'resources_destroyed': destroyed_count,
                'failures': failed_count,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
            print(f"✅ {agent_name.upper()} AGENT COMPLETED")
            print(f"   Duration: {duration:.1f} seconds")
            print(f"   Resources destroyed: {destroyed_count}")
            print(f"   Failures: {failed_count}")
            
            return phase_result
            
        except subprocess.TimeoutExpired:
            print(f"❌ {agent_name.upper()} AGENT TIMED OUT")
            return {
                'agent': agent_name,
                'start_time': start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'status': 'timeout',
                'error': 'Agent execution timed out after 30 minutes'
            }
            
        except Exception as e:
            print(f"❌ {agent_name.upper()} AGENT FAILED: {e}")
            return {
                'agent': agent_name,
                'start_time': start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'status': 'error',
                'error': str(e)
            }
    
    def orchestrate_account_closure(self):
        """Execute complete account closure process"""
        print(f"🔥🔥🔥 ACCOUNT CLOSURE ORCHESTRATOR 🔥🔥🔥")
        print(f"Account Profile: {self.profile_name}")
        print(f"⚠️  WARNING: COMPLETE ACCOUNT DESTRUCTION IN PROGRESS!")
        print("=" * 80)
        
        # Phase 1: Storage Destruction (parallel safe)
        print(f"\n📦 PHASE 1: STORAGE DESTRUCTION")
        storage_result = self.run_agent('storage_destruction_agent.py', 'Storage')
        self.closure_log['phases']['storage'] = storage_result
        
        # Phase 2: Compute Destruction (parallel safe)
        print(f"\n💻 PHASE 2: COMPUTE DESTRUCTION")
        compute_result = self.run_agent('compute_destruction_agent.py', 'Compute')
        self.closure_log['phases']['compute'] = compute_result
        
        # Wait between phases to allow AWS eventual consistency
        print(f"\n⏳ Waiting for AWS eventual consistency...")
        time.sleep(30)
        
        # Phase 3: Infrastructure Destruction (must be last)
        print(f"\n🏗️  PHASE 3: INFRASTRUCTURE DESTRUCTION")
        infra_result = self.run_agent('infrastructure_destruction_agent.py', 'Infrastructure')
        self.closure_log['phases']['infrastructure'] = infra_result
        
        # Calculate final summary
        self.closure_log['end_time'] = datetime.utcnow().isoformat()
        
        total_destroyed = 0
        total_failed = 0
        all_successful = True
        
        for phase_name, phase_data in self.closure_log['phases'].items():
            if phase_data.get('status') != 'success':
                all_successful = False
            
            total_destroyed += phase_data.get('resources_destroyed', 0)
            total_failed += phase_data.get('failures', 0)
        
        self.closure_log['summary']['total_resources_destroyed'] = total_destroyed
        self.closure_log['summary']['total_failures'] = total_failed
        self.closure_log['summary']['completion_status'] = 'completed' if all_successful else 'partial'
        
        # Save comprehensive results
        os.makedirs(self.results_dir, exist_ok=True)
        filename = f"{self.results_dir}/account_closure_{self.profile_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.closure_log, f, indent=2)
        
        # Generate final report
        self.generate_closure_report(filename)
        
        return self.closure_log
    
    def generate_closure_report(self, log_file: str):
        """Generate human-readable closure report"""
        print(f"\n🔥🔥🔥 ACCOUNT CLOSURE COMPLETE 🔥🔥🔥")
        print("=" * 80)
        print(f"Account Profile: {self.profile_name}")
        print(f"Completion Status: {self.closure_log['summary']['completion_status'].upper()}")
        print(f"Total Resources Destroyed: {self.closure_log['summary']['total_resources_destroyed']}")
        print(f"Total Failures: {self.closure_log['summary']['total_failures']}")
        
        print(f"\n📊 PHASE BREAKDOWN:")
        for phase_name, phase_data in self.closure_log['phases'].items():
            status_emoji = "✅" if phase_data.get('status') == 'success' else "❌"
            print(f"{status_emoji} {phase_name.title()}: {phase_data.get('resources_destroyed', 0)} destroyed, {phase_data.get('failures', 0)} failed")
        
        print(f"\n📁 Full log saved to: {log_file}")
        print(f"\n⚠️  ACCOUNT {self.profile_name} IS NOW READY FOR CLOSURE")
        
        # Create summary file
        summary_file = f"{self.results_dir}/CLOSURE_SUMMARY_{self.profile_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(summary_file, 'w') as f:
            f.write(f"AWS ACCOUNT CLOSURE SUMMARY\n")
            f.write(f"==========================\n\n")
            f.write(f"Account Profile: {self.profile_name}\n")
            f.write(f"Closure Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write(f"Status: {self.closure_log['summary']['completion_status'].upper()}\n\n")
            f.write(f"DESTRUCTION SUMMARY:\n")
            f.write(f"- Total Resources Destroyed: {self.closure_log['summary']['total_resources_destroyed']}\n")
            f.write(f"- Total Failures: {self.closure_log['summary']['total_failures']}\n\n")
            f.write(f"PHASE RESULTS:\n")
            for phase_name, phase_data in self.closure_log['phases'].items():
                f.write(f"- {phase_name.title()}: {phase_data.get('status', 'unknown').upper()}\n")
            f.write(f"\nFull details in: {log_file}\n")
        
        print(f"📋 Summary report: {summary_file}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 account_closure_orchestrator.py <profile_name>")
        print("Example: python3 account_closure_orchestrator.py Development-Admin")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    
    print(f"🚨 ACCOUNT CLOSURE ORCHESTRATOR")
    print(f"Profile: {profile_name}")
    print(f"⚠️  This will PERMANENTLY DESTROY ALL resources in the account!")
    
    response = input(f"\nType 'DESTROY {profile_name}' to confirm complete account destruction: ")
    if response != f'DESTROY {profile_name}':
        print("❌ Confirmation not received. Exiting.")
        sys.exit(1)
    
    orchestrator = AccountClosureOrchestrator(profile_name)
    orchestrator.orchestrate_account_closure()


if __name__ == "__main__":
    main()