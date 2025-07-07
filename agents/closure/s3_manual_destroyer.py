#!/usr/bin/env python3
"""
Manual S3 Destroyer - Destroys remaining S3 buckets for account closure
"""

import boto3
import sys
from datetime import datetime

def destroy_bucket(s3_client, bucket_name):
    """Completely destroy an S3 bucket"""
    print(f"🔥 DESTROYING BUCKET: {bucket_name}")
    
    try:
        # Step 1: Delete all object versions and delete markers
        print(f"  📋 Listing all versions...")
        paginator = s3_client.get_paginator('list_object_versions')
        
        for page in paginator.paginate(Bucket=bucket_name):
            # Collect all objects to delete
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
                    s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': batch, 'Quiet': True}
                    )
        
        # Step 2: Delete all current objects (non-versioned)
        print(f"  📋 Listing current objects...")
        paginator = s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=bucket_name):
            objects = page.get('Contents', [])
            if objects:
                print(f"    🗑️  Deleting {len(objects)} current objects...")
                delete_keys = [{'Key': obj['Key']} for obj in objects]
                for i in range(0, len(delete_keys), 1000):
                    batch = delete_keys[i:i+1000]
                    s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': batch, 'Quiet': True}
                    )
        
        # Step 3: Remove bucket policy if exists
        try:
            print(f"  🛡️  Removing bucket policy...")
            s3_client.delete_bucket_policy(Bucket=bucket_name)
        except:
            pass
        
        # Step 4: Remove lifecycle configuration if exists
        try:
            print(f"  ♻️  Removing lifecycle configuration...")
            s3_client.delete_bucket_lifecycle(Bucket=bucket_name)
        except:
            pass
        
        # Step 5: Remove CORS configuration if exists
        try:
            print(f"  🌐 Removing CORS configuration...")
            s3_client.delete_bucket_cors(Bucket=bucket_name)
        except:
            pass
        
        # Step 6: Delete the bucket itself
        print(f"  💀 Deleting bucket...")
        s3_client.delete_bucket(Bucket=bucket_name)
        
        print(f"  ✅ BUCKET DESTROYED: {bucket_name}")
        return True
        
    except Exception as e:
        print(f"  ❌ FAILED TO DESTROY: {bucket_name} - {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 s3_manual_destroyer.py <profile_name>")
        sys.exit(1)
    
    profile_name = sys.argv[1]
    print(f"🔥🔥🔥 S3 MANUAL DESTROYER for {profile_name} 🔥🔥🔥")
    
    # Initialize S3 client
    session = boto3.Session(profile_name=profile_name)
    s3 = session.client('s3')
    
    # List all buckets
    try:
        buckets = s3.list_buckets()['Buckets']
        print(f"📊 Found {len(buckets)} buckets to destroy")
        
        success_count = 0
        fail_count = 0
        
        for bucket in buckets:
            bucket_name = bucket['Name']
            if destroy_bucket(s3, bucket_name):
                success_count += 1
            else:
                fail_count += 1
        
        print(f"\n🔥 S3 DESTRUCTION COMPLETE!")
        print(f"   ✅ Successfully destroyed: {success_count}")
        print(f"   ❌ Failed to destroy: {fail_count}")
        
        if fail_count == 0:
            print("   🎉 ALL S3 BUCKETS DESTROYED!")
        
    except Exception as e:
        print(f"Error listing buckets: {e}")

if __name__ == "__main__":
    main()