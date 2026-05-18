"""
CLI commands for task execution in Brainlife.

This module provides command-line interface for pulling and executing
tasks from the Brainlife API on various resources.
"""

import argparse
import logging
import time
import json
from typing import Optional

from ..api.task_executor import TaskExecutor, create_task_executor
from ..api.resource import resource_query, resource_fetch
from ..api.project import project_query, project_fetch
from .utils import ensure_auth

logger = logging.getLogger("pybrainlife.cli.task")


def args(subparser):
    """Define command line arguments for task execution."""
    parser = subparser.add_parser(
        "task", 
        help="Task execution and management commands"
    )
    
    subparsers = parser.add_subparsers(dest="subcommand")
    
    # Execute tasks command
    execute_parser = subparsers.add_parser(
        "execute", 
        help="Pull and execute tasks from Brainlife API"
    )
    
    execute_parser.add_argument(
        "-r", "--resource", 
        help="Resource ID to use for execution"
    )
    execute_parser.add_argument(
        "-p", "--project", 
        help="Project ID to filter tasks"
    )
    execute_parser.add_argument(
        "-l", "--limit", 
        type=int, 
        default=10, 
        help="Maximum number of tasks to execute (default: 10)"
    )
    execute_parser.add_argument(
        "-s", "--status", 
        default="pending", 
        help="Task status to filter by (default: pending)"
    )
    execute_parser.add_argument(
        "--max-concurrent", 
        type=int, 
        default=1, 
        help="Maximum concurrent tasks (default: 1)"
    )
    execute_parser.add_argument(
        "--poll-interval", 
        type=int, 
        default=30, 
        help="Polling interval in seconds (default: 30)"
    )
    execute_parser.add_argument(
        "--timeout", 
        type=int, 
        help="Timeout in seconds for task execution"
    )
    execute_parser.add_argument(
        "--no-retry", 
        action="store_true", 
        help="Disable automatic retry of failed tasks"
    )
    execute_parser.add_argument(
        "--max-retries", 
        type=int, 
        default=3, 
        help="Maximum number of retries for failed tasks (default: 3)"
    )
    
    # Slurm options
    execute_parser.add_argument(
        "--slurm", 
        action="store_true", 
        help="Use Slurm cluster for task execution"
    )
    execute_parser.add_argument(
        "--slurm-host", 
        help="Slurm cluster hostname"
    )
    execute_parser.add_argument(
        "--slurm-user", 
        help="Slurm cluster username"
    )
    execute_parser.add_argument(
        "--slurm-key", 
        help="SSH key for Slurm cluster access"
    )
    
    # Output options
    execute_parser.add_argument(
        "--output", 
        help="Output file for execution results (JSON format)"
    )
    execute_parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Verbose output"
    )
    
    # List tasks command
    list_parser = subparsers.add_parser(
        "list", 
        help="List tasks from Brainlife API"
    )
    
    list_parser.add_argument(
        "-p", "--project", 
        help="Project ID to filter tasks"
    )
    list_parser.add_argument(
        "-r", "--resource", 
        help="Resource ID to filter tasks"
    )
    list_parser.add_argument(
        "-s", "--status", 
        help="Task status to filter by"
    )
    list_parser.add_argument(
        "-l", "--limit", 
        type=int, 
        default=20, 
        help="Maximum number of tasks to list (default: 20)"
    )
    list_parser.add_argument(
        "--format", 
        choices=["table", "json"], 
        default="table", 
        help="Output format (default: table)"
    )
    
    # Monitor tasks command
    monitor_parser = subparsers.add_parser(
        "monitor", 
        help="Monitor running tasks"
    )
    
    monitor_parser.add_argument(
        "-p", "--project", 
        help="Project ID to filter tasks"
    )
    monitor_parser.add_argument(
        "-r", "--resource", 
        help="Resource ID to filter tasks"
    )
    monitor_parser.add_argument(
        "--interval", 
        type=int, 
        default=30, 
        help="Monitoring interval in seconds (default: 30)"
    )
    monitor_parser.add_argument(
        "--duration", 
        type=int, 
        help="Monitoring duration in seconds (default: indefinite)"
    )
    
    # Status command
    status_parser = subparsers.add_parser(
        "status", 
        help="Get task execution status and summary"
    )
    
    status_parser.add_argument(
        "--format", 
        choices=["table", "json"], 
        default="table", 
        help="Output format (default: table)"
    )


def run(args):
    """Run task execution commands."""
    ensure_auth()
    
    if args.subcommand == "execute":
        return _execute_tasks(args)
    elif args.subcommand == "list":
        return _list_tasks(args)
    elif args.subcommand == "monitor":
        return _monitor_tasks(args)
    elif args.subcommand == "status":
        return _show_status(args)
    else:
        logger.error(f"Unknown subcommand: {args.subcommand}")
        return 1


def _execute_tasks(args):
    """Execute tasks from Brainlife API."""
    logger.info("Starting task execution...")
    
    # Validate resource if specified
    resource_id = getattr(args, 'resource', None)
    if resource_id:
        resource = resource_fetch(resource_id)
        if not resource:
            logger.error(f"Resource {resource_id} not found")
            return 1
        logger.info(f"Using resource: {resource.name}")
    
    # Validate project if specified
    project_id = getattr(args, 'project', None)
    if project_id:
        project = project_fetch(project_id)
        if not project:
            logger.error(f"Project {project_id} not found")
            return 1
        logger.info(f"Using project: {project.name}")
    
    # Create task executor
    executor = create_task_executor(
        resource_id=resource_id,
        project_id=project_id,
        use_slurm=getattr(args, 'slurm', False),
        slurm_host=getattr(args, 'slurm_host', None),
        slurm_user=getattr(args, 'slurm_user', None),
        slurm_key=getattr(args, 'slurm_key', None),
        max_concurrent_tasks=getattr(args, 'max_concurrent', 1),
        poll_interval=getattr(args, 'poll_interval', 30)
    )
    
    # Configure executor
    executor.config.retry_failed = not getattr(args, 'no_retry', False)
    executor.config.max_retries = getattr(args, 'max_retries', 3)
    executor.config.timeout = getattr(args, 'timeout', None)
    
    try:
        # Execute tasks
        results = executor.execute_tasks(
            status=getattr(args, 'status', 'pending'),
            limit=getattr(args, 'limit', 10)
        )
        
        # Display results
        _display_execution_results(results, executor, args)
        
        # Save results to file if specified
        output_file = getattr(args, 'output', None)
        if output_file:
            _save_results_to_file(results, executor, output_file)
        
        # Return appropriate exit code
        if executor.failed_tasks:
            return 1  # Some tasks failed
        else:
            return 0  # All tasks succeeded
            
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        return 1


def _list_tasks(args):
    """List tasks from Brainlife API."""
    logger.info("Listing tasks...")
    
    # Create a temporary executor to pull tasks
    executor = create_task_executor(
        resource_id=getattr(args, 'resource', None),
        project_id=getattr(args, 'project', None)
    )
    
    try:
        # Pull tasks
        tasks = executor.pull_tasks(
            status=getattr(args, 'status', None),
            limit=getattr(args, 'limit', 20)
        )
        
        if not tasks:
            print("No tasks found")
            return 0
        
        # Display tasks
        output_format = getattr(args, 'format', 'table')
        if output_format == 'json':
            print(json.dumps(tasks, indent=2))
        else:
            _display_tasks_table(tasks)
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        return 1


def _monitor_tasks(args):
    """Monitor running tasks."""
    logger.info("Starting task monitoring...")
    
    # Create executor
    executor = create_task_executor(
        resource_id=getattr(args, 'resource', None),
        project_id=getattr(args, 'project', None)
    )
    
    interval = getattr(args, 'interval', 30)
    duration = getattr(args, 'duration', None)
    
    start_time = time.time()
    
    try:
        while True:
            # Check if duration limit reached
            if duration and (time.time() - start_time) >= duration:
                logger.info("Monitoring duration reached")
                break
            
            # Pull running tasks
            running_tasks = executor.pull_tasks(status="running", limit=100)
            
            if running_tasks:
                print(f"\n=== Running Tasks ({len(running_tasks)}) ===")
                _display_tasks_table(running_tasks)
            else:
                print("\nNo running tasks found")
            
            # Wait for next check
            time.sleep(interval)
            
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Monitoring failed: {e}")
        return 1


def _show_status(args):
    """Show task execution status and summary."""
    logger.info("Getting task execution status...")
    
    # This would typically read from a status file or database
    # For now, show a placeholder message
    print("Task execution status:")
    print("  No execution history found")
    print("  Run 'bl task execute' to start task execution")
    
    return 0


def _display_execution_results(results, executor, args):
    """Display task execution results."""
    summary = executor.get_execution_summary()
    
    print("\n" + "="*60)
    print("TASK EXECUTION SUMMARY")
    print("="*60)
    print(f"Total tasks: {summary['total_tasks']}")
    print(f"Completed: {summary['completed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Running: {summary['running']}")
    print(f"Success rate: {summary['success_rate']:.1%}")
    
    if summary['average_duration'] > 0:
        print(f"Average duration: {summary['average_duration']:.2f}s")
    
    # Show detailed results if verbose
    if getattr(args, 'verbose', False):
        print("\nDETAILED RESULTS:")
        print("-" * 60)
        
        for result in executor.completed_tasks:
            print(f"✓ {result.task_id}: {result.status} ({result.duration:.2f}s)")
        
        for result in executor.failed_tasks:
            print(f"✗ {result.task_id}: {result.status}")
            if result.error_message:
                print(f"  Error: {result.error_message}")
    
    print("="*60)


def _display_tasks_table(tasks):
    """Display tasks in table format."""
    if not tasks:
        print("No tasks found")
        return
    
    # Print header
    print(f"{'Task ID':<20} {'Name':<30} {'Status':<12} {'Created':<20}")
    print("-" * 82)
    
    # Print tasks
    for task in tasks:
        task_id = task.get('_id', task.get('id', 'unknown'))[:18]
        name = task.get('name', 'unknown')[:28]
        status = task.get('status', 'unknown')
        created = task.get('created', 'unknown')[:18]
        
        print(f"{task_id:<20} {name:<30} {status:<12} {created:<20}")


def _save_results_to_file(results, executor, output_file):
    """Save execution results to file."""
    try:
        summary = executor.get_execution_summary()
        
        output_data = {
            "summary": summary,
            "completed_tasks": [
                {
                    "task_id": r.task_id,
                    "status": r.status,
                    "duration": r.duration,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "slurm_job_id": r.slurm_job_id
                }
                for r in executor.completed_tasks
            ],
            "failed_tasks": [
                {
                    "task_id": r.task_id,
                    "status": r.status,
                    "duration": r.duration,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "error_message": r.error_message,
                    "slurm_job_id": r.slurm_job_id
                }
                for r in executor.failed_tasks
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        logger.info(f"Results saved to {output_file}")
        
    except Exception as e:
        logger.error(f"Failed to save results to file: {e}")

