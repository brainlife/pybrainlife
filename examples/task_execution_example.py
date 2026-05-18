#!/usr/bin/env python3
"""
Example script demonstrating task execution with Brainlife.

This script shows how to:
1. Pull tasks from the Brainlife API
2. Execute tasks locally or on Slurm clusters
3. Monitor task execution
4. Handle results and errors
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add pybrainlife to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pybrainlife.api.task_executor import TaskExecutor, create_task_executor, TaskExecutionConfig
from pybrainlife.api.slurm import SlurmCluster, SlurmConfig

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_basic_task_execution():
    """Example of basic task execution."""
    print("=== Basic Task Execution ===")
    
    # Create task executor for local execution
    executor = create_task_executor(
        resource_id=None,  # Use default resource
        project_id=None,   # Execute tasks from all projects
        use_slurm=False,   # Use local execution
        max_concurrent_tasks=2,
        poll_interval=10
    )
    
    try:
        # Pull tasks from API
        tasks = executor.pull_tasks(status="pending", limit=5)
        
        if not tasks:
            print("No pending tasks found")
            return
        
        print(f"Found {len(tasks)} pending tasks")
        
        # Execute tasks
        results = executor.execute_tasks(status="pending", limit=3)
        
        # Display results
        summary = executor.get_execution_summary()
        print(f"\nExecution Summary:")
        print(f"  Total tasks: {summary['total_tasks']}")
        print(f"  Completed: {summary['completed']}")
        print(f"  Failed: {summary['failed']}")
        print(f"  Success rate: {summary['success_rate']:.1%}")
        
    except Exception as e:
        print(f"Error: {e}")
        print("Note: This example requires a valid Brainlife authentication")


def example_slurm_task_execution():
    """Example of Slurm-based task execution."""
    print("\n=== Slurm Task Execution ===")
    
    # Create Slurm cluster connection
    slurm_cluster = SlurmCluster(
        hostname=None,  # Use local Slurm for demo
        username=None,
        ssh_key=None,
        work_dir="/tmp/brainlife_demo"
    )
    
    try:
        # Test cluster connection
        cluster_info = slurm_cluster.get_cluster_info()
        print(f"Connected to Slurm cluster: {cluster_info['hostname']}")
        
        # Create task executor with Slurm
        executor = create_task_executor(
            resource_id=None,
            project_id=None,
            use_slurm=True,
            slurm_cluster=slurm_cluster,
            max_concurrent_tasks=1,
            poll_interval=15
        )
        
        # Pull and execute tasks
        tasks = executor.pull_tasks(status="pending", limit=2)
        
        if tasks:
            print(f"Found {len(tasks)} tasks for Slurm execution")
            
            # Execute tasks on Slurm
            results = executor.execute_tasks(status="pending", limit=2)
            
            # Display results
            for result in executor.completed_tasks:
                print(f"✓ Task {result.task_id} completed in {result.duration:.2f}s")
                if result.slurm_job_id:
                    print(f"  Slurm job ID: {result.slurm_job_id}")
            
            for result in executor.failed_tasks:
                print(f"✗ Task {result.task_id} failed: {result.error_message}")
        
    except Exception as e:
        print(f"Error: {e}")
        print("Note: This example requires a local Slurm installation")


def example_project_specific_execution():
    """Example of project-specific task execution."""
    print("\n=== Project-Specific Task Execution ===")
    
    # Example project ID (replace with actual project ID)
    project_id = "example_project_id"
    
    executor = create_task_executor(
        resource_id=None,
        project_id=project_id,
        use_slurm=False,
        max_concurrent_tasks=1
    )
    
    try:
        # Pull tasks from specific project
        tasks = executor.pull_tasks(status="pending", limit=5)
        
        print(f"Found {len(tasks)} tasks in project {project_id}")
        
        # Display task information
        for task in tasks:
            task_id = task.get('_id', 'unknown')
            task_name = task.get('name', 'unknown')
            task_status = task.get('status', 'unknown')
            print(f"  Task {task_id}: {task_name} ({task_status})")
        
        # Execute tasks
        if tasks:
            results = executor.execute_tasks(status="pending", limit=3)
            print(f"Executed {len(results)} tasks")
        
    except Exception as e:
        print(f"Error: {e}")


def example_resource_specific_execution():
    """Example of resource-specific task execution."""
    print("\n=== Resource-Specific Task Execution ===")
    
    # Example resource ID (replace with actual resource ID)
    resource_id = "example_resource_id"
    
    executor = create_task_executor(
        resource_id=resource_id,
        project_id=None,
        use_slurm=False,
        max_concurrent_tasks=1
    )
    
    try:
        # Pull tasks for specific resource
        tasks = executor.pull_tasks(status="pending", limit=5)
        
        print(f"Found {len(tasks)} tasks for resource {resource_id}")
        
        # Execute tasks
        if tasks:
            results = executor.execute_tasks(status="pending", limit=2)
            print(f"Executed {len(results)} tasks")
        
    except Exception as e:
        print(f"Error: {e}")


def example_advanced_configuration():
    """Example of advanced task execution configuration."""
    print("\n=== Advanced Configuration ===")
    
    # Create custom configuration
    config = TaskExecutionConfig(
        resource_id=None,
        project_id=None,
        max_concurrent_tasks=3,
        poll_interval=20,
        timeout=3600,  # 1 hour timeout
        retry_failed=True,
        max_retries=2,
        use_slurm=False
    )
    
    # Create executor with custom config
    executor = TaskExecutor(config)
    
    try:
        # Pull tasks with custom settings
        tasks = executor.pull_tasks(status="pending", limit=10)
        
        print(f"Configuration:")
        print(f"  Max concurrent tasks: {config.max_concurrent_tasks}")
        print(f"  Poll interval: {config.poll_interval}s")
        print(f"  Timeout: {config.timeout}s")
        print(f"  Retry failed: {config.retry_failed}")
        print(f"  Max retries: {config.max_retries}")
        
        print(f"\nFound {len(tasks)} tasks")
        
        # Execute with custom configuration
        if tasks:
            results = executor.execute_tasks(status="pending", limit=5)
            print(f"Executed {len(results)} tasks with advanced configuration")
        
    except Exception as e:
        print(f"Error: {e}")


def example_monitoring_and_status():
    """Example of task monitoring and status reporting."""
    print("\n=== Task Monitoring and Status ===")
    
    executor = create_task_executor(
        max_concurrent_tasks=2,
        poll_interval=5
    )
    
    try:
        # Start monitoring
        print("Starting task monitoring...")
        
        # Pull tasks
        tasks = executor.pull_tasks(status="running", limit=10)
        
        if tasks:
            print(f"Monitoring {len(tasks)} running tasks")
            
            # Simulate monitoring loop
            for i in range(3):  # Monitor for 3 iterations
                print(f"\nMonitoring iteration {i+1}")
                
                # Check task status
                running_tasks = executor.pull_tasks(status="running", limit=10)
                completed_tasks = executor.pull_tasks(status="completed", limit=10)
                failed_tasks = executor.pull_tasks(status="failed", limit=10)
                
                print(f"  Running: {len(running_tasks)}")
                print(f"  Completed: {len(completed_tasks)}")
                print(f"  Failed: {len(failed_tasks)}")
                
                # Wait before next check
                time.sleep(2)
        else:
            print("No running tasks to monitor")
        
        # Get execution summary
        summary = executor.get_execution_summary()
        print(f"\nExecution Summary:")
        print(f"  Total tasks: {summary['total_tasks']}")
        print(f"  Completed: {summary['completed']}")
        print(f"  Failed: {summary['failed']}")
        print(f"  Running: {summary['running']}")
        print(f"  Success rate: {summary['success_rate']:.1%}")
        
    except Exception as e:
        print(f"Error: {e}")


def example_error_handling():
    """Example of error handling in task execution."""
    print("\n=== Error Handling ===")
    
    executor = create_task_executor(
        retry_failed=True,
        max_retries=2,
        max_concurrent_tasks=1
    )
    
    try:
        # Simulate task execution with potential errors
        print("Testing error handling...")
        
        # Pull tasks
        tasks = executor.pull_tasks(status="pending", limit=3)
        
        if tasks:
            print(f"Found {len(tasks)} tasks for error handling test")
            
            # Execute tasks with error handling
            results = executor.execute_tasks(status="pending", limit=2)
            
            # Display results
            print(f"\nResults:")
            print(f"  Completed: {len(executor.completed_tasks)}")
            print(f"  Failed: {len(executor.failed_tasks)}")
            
            # Show error details
            for result in executor.failed_tasks:
                print(f"  Failed task {result.task_id}: {result.error_message}")
        
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Run all examples."""
    print("Brainlife Task Execution Examples")
    print("=" * 50)
    
    # Run examples
    example_basic_task_execution()
    example_slurm_task_execution()
    example_project_specific_execution()
    example_resource_specific_execution()
    example_advanced_configuration()
    example_monitoring_and_status()
    example_error_handling()
    
    print("\n" + "=" * 50)
    print("Examples completed!")
    print("\nTo use these features:")
    print("1. Set up Brainlife authentication")
    print("2. Use 'bl task execute' command for task execution")
    print("3. Use 'bl task list' command to view tasks")
    print("4. Use 'bl task monitor' command for real-time monitoring")
    print("5. Configure Slurm integration for HPC execution")


if __name__ == "__main__":
    main()

