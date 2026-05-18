#!/usr/bin/env python3
"""
Example script demonstrating Slurm cluster integration with Brainlife.

This script shows how to:
1. Connect to a Slurm cluster
2. Submit jobs
3. Monitor job execution
4. Integrate with Brainlife task execution
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add pybrainlife to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pybrainlife.api.slurm import SlurmCluster, SlurmConfig, create_brainlife_job_script

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_basic_slurm_usage():
    """Example of basic Slurm cluster usage."""
    print("=== Basic Slurm Cluster Usage ===")
    
    # Create cluster connection (use None for local Slurm)
    cluster = SlurmCluster(
        hostname=None,  # Use local Slurm for demo
        username=None,
        ssh_key=None,
        work_dir="/tmp/brainlife_demo"
    )
    
    try:
        # Get cluster information
        cluster_info = cluster.get_cluster_info()
        print(f"Cluster hostname: {cluster_info['hostname']}")
        print(f"Available partitions: {list(cluster_info['partitions'].keys())}")
        
        # Get queue status
        jobs = cluster.get_queue_status()
        print(f"Jobs in queue: {len(jobs)}")
        
        # Create a simple job script
        job_script = """#!/bin/bash
echo "Hello from Slurm job!"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Node: ${SLURM_JOB_NODELIST}"
echo "CPUs: ${SLURM_CPUS_PER_TASK}"
echo "Memory: ${SLURM_MEM_PER_CPU}"
sleep 10
echo "Job completed successfully!"
"""
        
        # Create Slurm configuration
        config = SlurmConfig(
            partition="default",
            nodes=1,
            cpus=1,
            memory="1G",
            time_limit="00:05:00"
        )
        
        # Submit job
        job = cluster.submit_job(
            script_content=job_script,
            job_name="brainlife_demo_job",
            config=config,
            wait=True  # Wait for completion
        )
        
        print(f"Job completed with status: {job.status}")
        if job.exit_code is not None:
            print(f"Exit code: {job.exit_code}")
            
    except Exception as e:
        print(f"Error: {e}")
        print("Note: This example requires a local Slurm installation")


def example_brainlife_integration():
    """Example of Brainlife task integration with Slurm."""
    print("\n=== Brainlife-Slurm Integration ===")
    
    # Mock Brainlife task data
    task_config = {
        "id": "task_001",
        "app_id": "app_001",
        "project_id": "project_001",
        "inputs": {"t1": "dataset_001"},
        "config": {"param1": "value1"}
    }
    
    app_config = {
        "name": "brainlife_freesurfer",
        "version": "7.2.0",
        "container": "brainlife/freesurfer:7.2.0"
    }
    
    inputs = {
        "t1": "dataset_001",
        "subject": "sub-001"
    }
    
    # Create Brainlife job script
    job_script = create_brainlife_job_script(
        task_config=task_config,
        app_config=app_config,
        inputs=inputs
    )
    
    print("Generated Brainlife job script:")
    print("=" * 50)
    print(job_script)
    print("=" * 50)
    
    # Create Slurm configuration for Brainlife
    config = SlurmConfig(
        partition="compute",
        nodes=1,
        cpus=4,
        memory="8G",
        time_limit="02:00:00",
        account="brainlife_account",
        qos="normal",
        work_dir="/scratch/brainlife",
        output_dir="/scratch/brainlife/outputs",
        error_dir="/scratch/brainlife/errors",
        environment={
            "BRAINLIFE_TOKEN": "your_token_here",
            "SINGULARITY_CACHEDIR": "/scratch/singularity_cache"
        }
    )
    
    print(f"Slurm configuration:")
    print(f"  Partition: {config.partition}")
    print(f"  Nodes: {config.nodes}")
    print(f"  CPUs: {config.cpus}")
    print(f"  Memory: {config.memory}")
    print(f"  Time limit: {config.time_limit}")
    print(f"  Account: {config.account}")
    print(f"  Work directory: {config.work_dir}")


def example_resource_configuration():
    """Example of resource configuration for Slurm."""
    print("\n=== Resource Configuration Example ===")
    
    # Example resource configuration
    resource_config = {
        "name": "HPC Cluster Resource",
        "config": {
            "slurm": {
                "partition": "compute",
                "nodes": 1,
                "cpus": 8,
                "memory": "32G",
                "time_limit": "04:00:00",
                "account": "research_account",
                "qos": "normal",
                "constraint": "skylake",
                "gres": "gpu:1",
                "mail_type": "END,FAIL",
                "mail_user": "researcher@university.edu",
                "work_dir": "/scratch/brainlife",
                "output_dir": "/scratch/brainlife/outputs",
                "error_dir": "/scratch/brainlife/errors",
                "environment": {
                    "MODULEPATH": "/opt/modules",
                    "SINGULARITY_CACHEDIR": "/scratch/singularity_cache",
                    "TMPDIR": "/scratch/tmp"
                }
            }
        },
        "envs": {
            "SLURM_CLUSTER": "main_cluster",
            "SLURM_PARTITION": "compute",
            "SLURM_ACCOUNT": "research_account"
        }
    }
    
    # Convert to SlurmConfig
    from pybrainlife.api.slurm import create_slurm_config_from_resource
    
    slurm_config = create_slurm_config_from_resource(resource_config["config"])
    
    print("Resource configuration:")
    print(f"  Name: {resource_config['name']}")
    print(f"  Slurm partition: {slurm_config.partition}")
    print(f"  Nodes: {slurm_config.nodes}")
    print(f"  CPUs: {slurm_config.cpus}")
    print(f"  Memory: {slurm_config.memory}")
    print(f"  Time limit: {slurm_config.time_limit}")
    print(f"  Account: {slurm_config.account}")
    print(f"  QOS: {slurm_config.qos}")
    print(f"  Constraint: {slurm_config.constraint}")
    print(f"  GRES: {slurm_config.gres}")
    print(f"  Mail type: {slurm_config.mail_type}")
    print(f"  Mail user: {slurm_config.mail_user}")
    print(f"  Work directory: {slurm_config.work_dir}")
    print(f"  Environment variables: {slurm_config.environment}")


def example_job_monitoring():
    """Example of job monitoring and management."""
    print("\n=== Job Monitoring Example ===")
    
    cluster = SlurmCluster(work_dir="/tmp/brainlife_demo")
    
    try:
        # Get current queue
        jobs = cluster.get_queue_status()
        
        if jobs:
            print("Current jobs in queue:")
            print(f"{'Job ID':<10} {'Name':<20} {'Status':<12} {'Partition':<12}")
            print("-" * 60)
            
            for job in jobs:
                print(f"{job.job_id:<10} {job.name:<20} {job.status:<12} {job.partition:<12}")
        else:
            print("No jobs currently in queue")
            
        # Example of monitoring a specific job
        if jobs:
            job_id = jobs[0].job_id
            print(f"\nMonitoring job {job_id}...")
            
            job_status = cluster.get_job_status(job_id)
            print(f"Job status: {job_status.status}")
            print(f"Job name: {job_status.name}")
            print(f"Partition: {job_status.partition}")
            print(f"Nodes: {job_status.nodes}")
            print(f"CPUs: {job_status.cpus}")
            print(f"Memory: {job_status.memory}")
            print(f"Time limit: {job_status.time_limit}")
            print(f"Submit time: {job_status.submit_time}")
            
            if job_status.start_time:
                print(f"Start time: {job_status.start_time}")
            if job_status.end_time:
                print(f"End time: {job_status.end_time}")
            if job_status.exit_code is not None:
                print(f"Exit code: {job_status.exit_code}")
                
    except Exception as e:
        print(f"Error monitoring jobs: {e}")
        print("Note: This example requires a local Slurm installation")


def main():
    """Run all examples."""
    print("Brainlife Slurm Integration Examples")
    print("=" * 50)
    
    # Run examples
    example_basic_slurm_usage()
    example_brainlife_integration()
    example_resource_configuration()
    example_job_monitoring()
    
    print("\n" + "=" * 50)
    print("Examples completed!")
    print("\nTo use these features:")
    print("1. Set up SSH access to your Slurm cluster")
    print("2. Configure a Brainlife resource with Slurm settings")
    print("3. Use 'bl resource slurm' commands for cluster management")
    print("4. Use 'bl resource pull --slurm' for task execution")


if __name__ == "__main__":
    main()

