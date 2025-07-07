#!/usr/bin/env python3
"""
Targeted S3 Bucket Destroyer - Destroys specific remaining S3 buckets for account closure
"""

import boto3
import sys
import json
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError

class TargetedS3BucketDestroyer:
    def __init__(self, profile_name):
        self.profile_name = profile_name
        self.session = boto3.Session(profile_name=profile_name)
        self.s3_client = self.session.client('s3')
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'profile': profile_name,
            'buckets_processed': [],
            'summary': {
                'total_attempted': 0,
                'successful_deletions': 0,
                'failed_deletions': 0,
                'access_denied_errors': 0,
                'policy_restricted_errors': 0,
                'other_errors': 0
            }
        }
    
    def empty_bucket_contents(self, bucket_name):
        """Empty all objects and versions from a bucket"""
        print(f"  📋 Emptying bucket contents...")
        
        try:
            # Delete all object versions and delete markers
            paginator = self.s3_client.get_paginator('list_object_versions')
            
            for page in paginator.paginate(Bucket=bucket_name):
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
                if objects_to_delete:
                    print(f"    🗑️  Deleting {len(objects_to_delete)} versioned objects...")
                    for i in range(0, len(objects_to_delete), 1000):
                        batch = objects_to_delete[i:i+1000]
                        self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': batch, 'Quiet': True}
                        )
            
            # Delete all current objects (non-versioned)
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=bucket_name):
                objects = page.get('Contents', [])
                if objects:
                    print(f"    🗑️  Deleting {len(objects)} current objects...")
                    delete_keys = [{'Key': obj['Key']} for obj in objects]
                    for i in range(0, len(delete_keys), 1000):
                        batch = delete_keys[i:i+1000]
                        self.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': batch, 'Quiet': True}
                        )
            
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'AccessDenied':
                print(f"    ❌ Access denied while emptying bucket contents")
                return False
            elif error_code == 'NoSuchBucket':
                print(f"    ℹ️  Bucket doesn't exist (already deleted or never existed)")
                return True
            else:
                print(f"    ❌ Error emptying bucket: {e}")
                return False
    
    def remove_bucket_configurations(self, bucket_name):
        """Remove bucket policies and configurations that might prevent deletion"""
        print(f"  🛠️  Removing bucket configurations...")
        
        configurations_removed = []
        
        # Remove bucket policy
        try:
            self.s3_client.delete_bucket_policy(Bucket=bucket_name)
            configurations_removed.append("bucket_policy")
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'NoSuchBucketPolicy':
                print(f"    ⚠️  Could not remove bucket policy: {e}")
        
        # Remove lifecycle configuration
        try:
            self.s3_client.delete_bucket_lifecycle(Bucket=bucket_name)
            configurations_removed.append("lifecycle")
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'NoSuchLifecycleConfiguration':
                print(f"    ⚠️  Could not remove lifecycle configuration: {e}")
        
        # Remove CORS configuration
        try:
            self.s3_client.delete_bucket_cors(Bucket=bucket_name)
            configurations_removed.append("cors")
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'NoSuchCORSConfiguration':
                print(f"    ⚠️  Could not remove CORS configuration: {e}")
        
        # Remove versioning configuration
        try:
            self.s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Suspended'}
            )
            configurations_removed.append("versioning")
        except ClientError as e:
            print(f"    ⚠️  Could not suspend versioning: {e}")
        
        # Remove notification configuration
        try:
            self.s3_client.put_bucket_notification_configuration(
                Bucket=bucket_name,
                NotificationConfiguration={}
            )
            configurations_removed.append("notifications")
        except ClientError as e:
            print(f"    ⚠️  Could not remove notification configuration: {e}")
        
        if configurations_removed:
            print(f"    ✅ Removed configurations: {', '.join(configurations_removed)}")
        
        return configurations_removed
    
    def destroy_bucket(self, bucket_name):
        """Completely destroy an S3 bucket"""
        print(f"\n🔥 DESTROYING BUCKET: {bucket_name}")
        
        bucket_result = {
            'bucket_name': bucket_name,
            'status': 'failed',
            'error_type': None,
            'error_message': None,
            'configurations_removed': [],
            'steps_completed': []
        }
        
        try:
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                bucket_result['steps_completed'].append('bucket_exists_check')
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == 'NoSuchBucket':
                    print(f"  ℹ️  Bucket {bucket_name} doesn't exist (already deleted)")
                    bucket_result['status'] = 'success'
                    bucket_result['error_message'] = 'Bucket already deleted'
                    return bucket_result
                elif error_code == 'AccessDenied':
                    print(f"  ❌ Access denied to bucket {bucket_name}")
                    bucket_result['error_type'] = 'access_denied'
                    bucket_result['error_message'] = str(e)
                    return bucket_result
                else:
                    raise e
            
            # Step 1: Empty bucket contents
            if self.empty_bucket_contents(bucket_name):
                bucket_result['steps_completed'].append('empty_contents')
            else:
                bucket_result['error_type'] = 'empty_failed'
                return bucket_result
            
            # Step 2: Remove bucket configurations
            configurations_removed = self.remove_bucket_configurations(bucket_name)
            bucket_result['configurations_removed'] = configurations_removed
            bucket_result['steps_completed'].append('remove_configurations')
            
            # Step 3: Delete the bucket itself
            print(f"  💀 Deleting bucket...")
            self.s3_client.delete_bucket(Bucket=bucket_name)
            bucket_result['steps_completed'].append('delete_bucket')
            
            print(f"  ✅ BUCKET DESTROYED: {bucket_name}")
            bucket_result['status'] = 'success'
            return bucket_result
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = str(e)
            
            if error_code == 'AccessDenied':
                print(f"  ❌ ACCESS DENIED: {bucket_name}")
                print(f"     This bucket may be protected by service control policies")
                bucket_result['error_type'] = 'access_denied'
                self.results['summary']['access_denied_errors'] += 1
            elif error_code == 'BucketNotEmpty':
                print(f"  ❌ BUCKET NOT EMPTY: {bucket_name}")
                print(f"     Some objects may still remain or be protected")
                bucket_result['error_type'] = 'bucket_not_empty'
            elif 'ServiceControlPolicy' in error_message or 'SCP' in error_message:
                print(f"  ❌ SERVICE CONTROL POLICY RESTRICTION: {bucket_name}")
                bucket_result['error_type'] = 'policy_restricted'
                self.results['summary']['policy_restricted_errors'] += 1
            else:
                print(f"  ❌ UNEXPECTED ERROR: {bucket_name} - {error_message}")
                bucket_result['error_type'] = 'other_error'
                self.results['summary']['other_errors'] += 1
            
            bucket_result['error_message'] = error_message
            return bucket_result
        
        except Exception as e:
            print(f"  ❌ UNEXPECTED ERROR: {bucket_name} - {e}")
            bucket_result['error_type'] = 'unexpected_error'
            bucket_result['error_message'] = str(e)
            self.results['summary']['other_errors'] += 1
            return bucket_result
    
    def destroy_target_buckets(self, target_buckets):
        """Destroy specific target buckets"""
        print(f"🔥🔥🔥 TARGETED S3 BUCKET DESTROYER for {self.profile_name} 🔥🔥🔥")
        print(f"📊 Targeting {len(target_buckets)} specific buckets for destruction")
        
        self.results['summary']['total_attempted'] = len(target_buckets)
        
        for bucket_name in target_buckets:
            bucket_result = self.destroy_bucket(bucket_name)
            self.results['buckets_processed'].append(bucket_result)
            
            if bucket_result['status'] == 'success':
                self.results['summary']['successful_deletions'] += 1
            else:
                self.results['summary']['failed_deletions'] += 1
        
        return self.results
    
    def print_summary(self):
        """Print a summary of the destruction operation"""
        print(f"\n🔥 TARGETED S3 BUCKET DESTRUCTION COMPLETE!")
        print(f"   📊 Total buckets attempted: {self.results['summary']['total_attempted']}")
        print(f"   ✅ Successfully destroyed: {self.results['summary']['successful_deletions']}")
        print(f"   ❌ Failed to destroy: {self.results['summary']['failed_deletions']}")
        
        if self.results['summary']['access_denied_errors'] > 0:
            print(f"   🚫 Access denied errors: {self.results['summary']['access_denied_errors']}")
        
        if self.results['summary']['policy_restricted_errors'] > 0:
            print(f"   🛡️  Policy restricted errors: {self.results['summary']['policy_restricted_errors']}")
        
        if self.results['summary']['other_errors'] > 0:
            print(f"   ⚠️  Other errors: {self.results['summary']['other_errors']}")
        
        if self.results['summary']['failed_deletions'] == 0:
            print("   🎉 ALL TARGET BUCKETS DESTROYED!")
        
        # Print detailed results for failed buckets
        failed_buckets = [b for b in self.results['buckets_processed'] if b['status'] == 'failed']
        if failed_buckets:
            print(f"\n❌ FAILED BUCKET DETAILS:")
            for bucket in failed_buckets:
                print(f"   • {bucket['bucket_name']}: {bucket['error_type']} - {bucket['error_message']}")
    
    def save_results(self, output_file=None):
        """Save detailed results to a JSON file"""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"/Users/bc/Desktop/@modulairhr_aws/infra-decom-logs/agents/closure/results/targeted_s3_destruction_{self.profile_name}_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"📄 Detailed results saved to: {output_file}")
        return output_file

def main():
    # Target buckets for Development-Admin account
    TARGET_BUCKETS = [
        "aws-config-bucket-134388504287",
        "aws-config-bucket-134388504287-us-east-1",
        "cdk-hnb659fds-assets-134388504287-us-east-1",
        "modulairhr-cloudfront-logs-dev-134388504287",
        "modulairhr-lambda-artifacts-134388504287"
    ]
    
    if len(sys.argv) != 2:
        print("Usage: python3 targeted_s3_bucket_destroyer.py <profile_name>")
        print("\nThis script will attempt to destroy the following buckets:")
        for bucket in TARGET_BUCKETS:
            print(f"  • {bucket}")
        print("\nNote: Some buckets may be protected by service control policies.")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    
    try:
        destroyer = TargetedS3BucketDestroyer(profile_name)
        results = destroyer.destroy_target_buckets(TARGET_BUCKETS)
        destroyer.print_summary()
        destroyer.save_results()
        
        # Exit with error code if any buckets failed to delete
        if results['summary']['failed_deletions'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except NoCredentialsError:
        print(f"❌ Error: No credentials found for profile '{profile_name}'")
        print("Please ensure your AWS credentials are configured correctly.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()