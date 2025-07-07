#!/usr/bin/env python3
"""
Storage Destruction Agent - Destroys ALL storage resources for account closure
"""

import json
import boto3
import concurrent.futures
from datetime import datetime
import os
import sys
from typing import Dict, List, Any

class StorageDestructionAgent:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.account_id = self.get_account_id()
        self.destruction_log = {
            'account_id': self.account_id,
            'profile_name': profile_name,
            'start_time': datetime.utcnow().isoformat(),
            'agent_type': 'storage_destruction',
            'destroyed': [],
            'failed': [],
            'summary': {'s3_buckets': 0, 'ebs_volumes': 0, 'snapshots': 0, 'failed': 0}
        }
        
    def get_account_id(self) -> str:
        try:
            sts = self.session.client('sts')
            return sts.get_caller_identity()['Account']
        except Exception as e:
            print(f"Error getting account ID: {e}")
            return "unknown"
    
    def destroy_s3_buckets(self):
        """Destroy ALL S3 buckets"""
        print("🔥 DESTROYING ALL S3 BUCKETS...")
        s3 = self.session.client('s3')
        
        try:
            buckets = s3.list_buckets()['Buckets']
            print(f"  Found {len(buckets)} S3 buckets to destroy")
            
            for bucket in buckets:
                bucket_name = bucket['Name']
                try:
                    print(f"  🗑️  Destroying bucket: {bucket_name}")
                    
                    # Remove bucket policy if exists
                    try:
                        s3.delete_bucket_policy(Bucket=bucket_name)
                    except:
                        pass
                    
                    # Remove bucket lifecycle if exists
                    try:
                        s3.delete_bucket_lifecycle(Bucket=bucket_name)
                    except:
                        pass
                    
                    # Remove bucket versioning and delete all versions
                    try:
                        paginator = s3.get_paginator('list_object_versions')
                        for page in paginator.paginate(Bucket=bucket_name):
                            # Delete all versions and delete markers
                            objects_to_delete = []
                            
                            # Add all versions
                            for version in page.get('Versions', []):
                                objects_to_delete.append({
                                    'Key': version['Key'],
                                    'VersionId': version['VersionId']
                                })
                            
                            # Add all delete markers
                            for marker in page.get('DeleteMarkers', []):
                                objects_to_delete.append({
                                    'Key': marker['Key'],
                                    'VersionId': marker['VersionId']
                                })
                            
                            # Delete in batches of 1000
                            for i in range(0, len(objects_to_delete), 1000):
                                batch = objects_to_delete[i:i+1000]
                                if batch:
                                    s3.delete_objects(
                                        Bucket=bucket_name,
                                        Delete={'Objects': batch}
                                    )
                    except Exception as e:
                        print(f"    Error clearing versioned objects: {e}")
                    
                    # Delete all current objects
                    try:
                        paginator = s3.get_paginator('list_objects_v2')
                        for page in paginator.paginate(Bucket=bucket_name):
                            objects = page.get('Contents', [])
                            if objects:
                                delete_keys = [{'Key': obj['Key']} for obj in objects]
                                for i in range(0, len(delete_keys), 1000):
                                    batch = delete_keys[i:i+1000]
                                    s3.delete_objects(
                                        Bucket=bucket_name,
                                        Delete={'Objects': batch}
                                    )
                    except Exception as e:
                        print(f"    Error deleting objects: {e}")
                    
                    # Delete the bucket
                    s3.delete_bucket(Bucket=bucket_name)
                    print(f"    ✅ DESTROYED: {bucket_name}")
                    
                    self.destruction_log['destroyed'].append({
                        'type': 's3_bucket',
                        'id': bucket_name,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['s3_buckets'] += 1
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {bucket_name} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 's3_bucket',
                        'id': bucket_name,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
                    
        except Exception as e:
            print(f"Error listing S3 buckets: {e}")
    
    def destroy_ebs_volumes(self, region: str):
        """Destroy all EBS volumes in a region"""
        print(f"🔥 DESTROYING EBS VOLUMES in {region}...")
        ec2 = self.session.client('ec2', region_name=region)
        
        try:
            volumes = ec2.describe_volumes(
                Filters=[{'Name': 'state', 'Values': ['available']}]
            )['Volumes']
            
            print(f"  Found {len(volumes)} available EBS volumes to destroy")
            
            for volume in volumes:
                volume_id = volume['VolumeId']
                try:
                    print(f"  🗑️  Destroying volume: {volume_id}")
                    ec2.delete_volume(VolumeId=volume_id)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'ebs_volume',
                        'id': volume_id,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['ebs_volumes'] += 1
                    print(f"    ✅ DESTROYED: {volume_id}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {volume_id} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'ebs_volume',
                        'id': volume_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
                    
        except Exception as e:
            print(f"Error listing EBS volumes in {region}: {e}")
    
    def destroy_snapshots(self, region: str):
        """Destroy all owned EBS snapshots in a region"""
        print(f"🔥 DESTROYING EBS SNAPSHOTS in {region}...")
        ec2 = self.session.client('ec2', region_name=region)
        
        try:
            snapshots = ec2.describe_snapshots(OwnerIds=['self'])['Snapshots']
            print(f"  Found {len(snapshots)} snapshots to destroy")
            
            for snapshot in snapshots:
                snapshot_id = snapshot['SnapshotId']
                try:
                    print(f"  🗑️  Destroying snapshot: {snapshot_id}")
                    ec2.delete_snapshot(SnapshotId=snapshot_id)
                    
                    self.destruction_log['destroyed'].append({
                        'type': 'ebs_snapshot',
                        'id': snapshot_id,
                        'region': region,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                    self.destruction_log['summary']['snapshots'] += 1
                    print(f"    ✅ DESTROYED: {snapshot_id}")
                    
                except Exception as e:
                    print(f"    ❌ FAILED: {snapshot_id} - {e}")
                    self.destruction_log['failed'].append({
                        'type': 'ebs_snapshot',
                        'id': snapshot_id,
                        'region': region,
                        'error': str(e)
                    })
                    self.destruction_log['summary']['failed'] += 1
                    
        except Exception as e:
            print(f"Error listing snapshots in {region}: {e}")
    
    def destroy_all_storage(self):
        """Main destruction execution"""
        print(f"🔥🔥🔥 STORAGE DESTRUCTION AGENT - ACCOUNT {self.account_id} 🔥🔥🔥")
        print("⚠️  WARNING: ALL STORAGE RESOURCES WILL BE PERMANENTLY DESTROYED!")
        
        # Destroy S3 buckets first (global)
        self.destroy_s3_buckets()
        
        # Get all regions
        ec2 = self.session.client('ec2', region_name='us-east-1')
        regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
        
        # Destroy EBS resources in all regions in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all region tasks
            future_to_region = {}
            for region in regions:
                future_to_region[executor.submit(self.destroy_ebs_volumes, region)] = region
                future_to_region[executor.submit(self.destroy_snapshots, region)] = region
            
            # Wait for all to complete
            for future in concurrent.futures.as_completed(future_to_region):
                region = future_to_region[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error processing region {region}: {e}")
        
        self.destruction_log['end_time'] = datetime.utcnow().isoformat()
        
        # Save results
        output_dir = "/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure/results"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{output_dir}/storage_destruction_{self.account_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.destruction_log, f, indent=2)
        
        print(f"\n🔥 STORAGE DESTRUCTION COMPLETE!")
        print(f"  S3 Buckets destroyed: {self.destruction_log['summary']['s3_buckets']}")
        print(f"  EBS Volumes destroyed: {self.destruction_log['summary']['ebs_volumes']}")
        print(f"  Snapshots destroyed: {self.destruction_log['summary']['snapshots']}")
        print(f"  Failed: {self.destruction_log['summary']['failed']}")
        print(f"  Results saved to: {filename}")
        
        return self.destruction_log


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 storage_destruction_agent.py <profile_name>")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    print(f"🔥 Starting Storage Destruction Agent for {profile_name}")
    
    agent = StorageDestructionAgent(profile_name)
    agent.destroy_all_storage()


if __name__ == "__main__":
    main()