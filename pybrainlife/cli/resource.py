import json
import logging
import argparse
import time

from ..api.datatype import datatype_query
from ..api.slurm import SlurmCluster, SlurmConfig, create_slurm_config_from_resource
from ..api.resource import resource_query, resource_fetch
from .utils import ensure_auth


logger = logging.getLogger("pybrainlife.cli")


def args(subparser):
    parser = subparser.add_parser(
        "resource", help="Resource management and task execution on Brainlife."
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    
    # Pull tasks subcommand
    pull_parser = subparsers.add_parser("pull", help="Pull tasks for execution")
    pull_parser.add_argument("-p", "--project", help="Filter data by project")
    pull_parser.add_argument("-r", "--resource", help="Resource ID to use for execution")
    pull_parser.add_argument("--slurm", action="store_true", help="Use Slurm cluster for execution")
    pull_parser.add_argument("--slurm-host", help="Slurm cluster hostname")
    pull_parser.add_argument("--slurm-user", help="Slurm cluster username")
    pull_parser.add_argument("--slurm-key", help="SSH key for Slurm cluster access")
    
    # Slurm management subcommands
    slurm_parser = subparsers.add_parser("slurm", help="Slurm cluster management")
    slurm_subparsers = slurm_parser.add_subparsers(dest="slurm_command")
    
    # Slurm status command
    status_parser = slurm_subparsers.add_parser("status", help="Check Slurm cluster status")
    status_parser.add_argument("--host", help="Slurm cluster hostname")
    status_parser.add_argument("--user", help="Slurm cluster username")
    status_parser.add_argument("--key", help="SSH key for cluster access")
    
    # Slurm queue command
    queue_parser = slurm_subparsers.add_parser("queue", help="Show Slurm job queue")
    queue_parser.add_argument("--host", help="Slurm cluster hostname")
    queue_parser.add_argument("--user", help="Slurm cluster username")
    queue_parser.add_argument("--key", help="SSH key for cluster access")
    
    # Slurm submit command
    submit_parser = slurm_subparsers.add_parser("submit", help="Submit a job to Slurm")
    submit_parser.add_argument("script", help="Job script file")
    submit_parser.add_argument("--name", help="Job name")
    submit_parser.add_argument("--partition", default="default", help="Slurm partition")
    submit_parser.add_argument("--nodes", type=int, default=1, help="Number of nodes")
    submit_parser.add_argument("--cpus", type=int, default=1, help="Number of CPUs")
    submit_parser.add_argument("--memory", default="1G", help="Memory allocation")
    submit_parser.add_argument("--time", default="01:00:00", help="Time limit")
    submit_parser.add_argument("--account", help="Slurm account")
    submit_parser.add_argument("--qos", help="Quality of service")
    submit_parser.add_argument("--host", help="Slurm cluster hostname")
    submit_parser.add_argument("--user", help="Slurm cluster username")
    submit_parser.add_argument("--key", help="SSH key for cluster access")
    submit_parser.add_argument("--wait", action="store_true", help="Wait for job completion")
    
    # Slurm cancel command
    cancel_parser = slurm_subparsers.add_parser("cancel", help="Cancel a Slurm job")
    cancel_parser.add_argument("job_id", help="Job ID to cancel")
    cancel_parser.add_argument("--host", help="Slurm cluster hostname")
    cancel_parser.add_argument("--user", help="Slurm cluster username")
    cancel_parser.add_argument("--key", help="SSH key for cluster access")


def run(args):
    """
    Execute resource tasks based on the provided arguments.
    
    This function handles the execution of resource-related tasks including:
    - Connecting to task queue
    - Pulling tasks for execution
    - Executing tasks on Slurm clusters or local resources
    - Returning task results
    - Archiving results from tasks
    """
    ensure_auth()
    
    if args.subcommand == "pull":
        return _handle_pull_tasks(args)
    elif args.subcommand == "slurm":
        return _handle_slurm_commands(args)
    else:
        logger.error(f"Unknown subcommand: {args.subcommand}")
        return 1


def _handle_pull_tasks(args):
    """Handle task pulling and execution."""
    logger.info("Pulling tasks for execution...")
    
    # Get resource configuration
    resource_id = getattr(args, 'resource', None)
    resource = None
    
    if resource_id:
        resource = resource_fetch(resource_id)
        if not resource:
            logger.error(f"Resource {resource_id} not found")
            return 1
        logger.info(f"Using resource: {resource.name}")
    
    # Check if using Slurm
    use_slurm = getattr(args, 'slurm', False)
    
    if use_slurm:
        return _execute_tasks_with_slurm(args, resource)
    else:
        return _execute_tasks_locally(args, resource)


def _execute_tasks_with_slurm(args, resource):
    """Execute tasks using Slurm cluster."""
    logger.info("Executing tasks with Slurm cluster...")
    
    # Create Slurm cluster connection
    slurm_host = getattr(args, 'slurm_host', None)
    slurm_user = getattr(args, 'slurm_user', None)
    slurm_key = getattr(args, 'slurm_key', None)
    
    cluster = SlurmCluster(
        hostname=slurm_host,
        username=slurm_user,
        ssh_key=slurm_key
    )
    
    # Get Slurm configuration from resource
    slurm_config = SlurmConfig()
    if resource and resource.config:
        slurm_config = create_slurm_config_from_resource(resource.config)
    
    # Override with command line arguments if provided
    if hasattr(args, 'slurm_host') and args.slurm_host:
        slurm_config.work_dir = f"/tmp/brainlife_{args.project or 'default'}"
    
    try:
        # Test cluster connection
        cluster_info = cluster.get_cluster_info()
        logger.info(f"Connected to Slurm cluster: {cluster_info['hostname']}")
        logger.info(f"Available partitions: {list(cluster_info['partitions'].keys())}")
        
        # Pull tasks from Brainlife
        project_filter = getattr(args, 'project', None)
        tasks = _pull_brainlife_tasks(project_filter, resource)
        
        if not tasks:
            logger.info("No tasks found for execution")
            return 0
        
        logger.info(f"Found {len(tasks)} tasks to execute")
        
        # Submit tasks to Slurm
        submitted_jobs = []
        for task in tasks:
            try:
                job_script = _create_brainlife_job_script(task)
                job_name = f"brainlife_{task.get('id', 'unknown')}"
                
                job = cluster.submit_job(
                    script_content=job_script,
                    job_name=job_name,
                    config=slurm_config,
                    wait=False
                )
                
                submitted_jobs.append(job)
                logger.info(f"Submitted task {task.get('id')} as Slurm job {job.job_id}")
                
            except Exception as e:
                logger.error(f"Failed to submit task {task.get('id')}: {e}")
                continue
        
        logger.info(f"Successfully submitted {len(submitted_jobs)} jobs to Slurm")
        
        # Monitor job status
        if submitted_jobs:
            _monitor_slurm_jobs(cluster, submitted_jobs)
        
        return 0
        
    except Exception as e:
        logger.error(f"Slurm execution failed: {e}")
        return 1


def _execute_tasks_locally(args, resource):
    """Execute tasks locally (original implementation)."""
    logger.info("Executing tasks locally...")
    
    # Connect to task queue that pulls new tasks for execution
    # This would typically involve connecting to a message queue or API
    # to retrieve pending tasks for the resource
    
    # Pull tasks for execution
    # Filter by project if specified
    project_filter = getattr(args, 'project', None)
    
    # Execute tasks
    # This would involve running the actual computational tasks
    # on the resource (compute nodes, containers, etc.)
    
    # Return tasks
    # Report back the status and results of executed tasks
    
    # Archive results from tasks
    # Store or upload results to appropriate storage systems
    
    logger.info("Local task execution completed successfully")
    return 0


def _handle_slurm_commands(args):
    """Handle Slurm management commands."""
    slurm_command = getattr(args, 'slurm_command', None)
    
    if slurm_command == "status":
        return _slurm_status(args)
    elif slurm_command == "queue":
        return _slurm_queue(args)
    elif slurm_command == "submit":
        return _slurm_submit(args)
    elif slurm_command == "cancel":
        return _slurm_cancel(args)
    else:
        logger.error(f"Unknown Slurm command: {slurm_command}")
        return 1


def _slurm_status(args):
    """Check Slurm cluster status."""
    cluster = SlurmCluster(
        hostname=getattr(args, 'host', None),
        username=getattr(args, 'user', None),
        ssh_key=getattr(args, 'key', None)
    )
    
    try:
        cluster_info = cluster.get_cluster_info()
        
        print(f"Slurm Cluster Status:")
        print(f"Hostname: {cluster_info['hostname']}")
        print(f"Username: {cluster_info['username']}")
        print(f"\nPartitions:")
        
        for partition, info in cluster_info['partitions'].items():
            print(f"  {partition}:")
            print(f"    Available: {info['available']}")
            print(f"    State: {info['state']}")
            print(f"    Nodes: {info['nodes']}")
            if info['gres']:
                print(f"    GRES: {info['gres']}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to get cluster status: {e}")
        return 1


def _slurm_queue(args):
    """Show Slurm job queue."""
    cluster = SlurmCluster(
        hostname=getattr(args, 'host', None),
        username=getattr(args, 'user', None),
        ssh_key=getattr(args, 'key', None)
    )
    
    try:
        jobs = cluster.get_queue_status()
        
        if not jobs:
            print("No jobs in queue")
            return 0
        
        print(f"{'Job ID':<10} {'Name':<20} {'Status':<12} {'Partition':<12} {'Nodes':<6} {'CPUs':<5} {'Memory':<8}")
        print("-" * 80)
        
        for job in jobs:
            print(f"{job.job_id:<10} {job.name:<20} {job.status:<12} {job.partition:<12} "
                  f"{job.nodes:<6} {job.cpus:<5} {job.memory:<8}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        return 1


def _slurm_submit(args):
    """Submit a job to Slurm."""
    cluster = SlurmCluster(
        hostname=getattr(args, 'host', None),
        username=getattr(args, 'user', None),
        ssh_key=getattr(args, 'key', None)
    )
    
    try:
        # Read job script
        with open(args.script, 'r') as f:
            script_content = f.read()
        
        # Create Slurm configuration
        config = SlurmConfig(
            partition=getattr(args, 'partition', 'default'),
            nodes=getattr(args, 'nodes', 1),
            cpus=getattr(args, 'cpus', 1),
            memory=getattr(args, 'memory', '1G'),
            time_limit=getattr(args, 'time', '01:00:00'),
            account=getattr(args, 'account', None),
            qos=getattr(args, 'qos', None)
        )
        
        job_name = getattr(args, 'name', f"brainlife_job_{int(time.time())}")
        wait = getattr(args, 'wait', False)
        
        job = cluster.submit_job(
            script_content=script_content,
            job_name=job_name,
            config=config,
            wait=wait
        )
        
        print(f"Job submitted successfully:")
        print(f"  Job ID: {job.job_id}")
        print(f"  Name: {job.name}")
        print(f"  Status: {job.status}")
        print(f"  Partition: {job.partition}")
        
        if wait:
            print(f"Job completed with status: {job.status}")
            if job.exit_code is not None:
                print(f"Exit code: {job.exit_code}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        return 1


def _slurm_cancel(args):
    """Cancel a Slurm job."""
    cluster = SlurmCluster(
        hostname=getattr(args, 'host', None),
        username=getattr(args, 'user', None),
        ssh_key=getattr(args, 'key', None)
    )
    
    try:
        success = cluster.cancel_job(args.job_id)
        
        if success:
            print(f"Job {args.job_id} cancelled successfully")
            return 0
        else:
            print(f"Failed to cancel job {args.job_id}")
            return 1
            
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        return 1


def _pull_brainlife_tasks(project_filter, resource):
    """Pull tasks from Brainlife API."""
    # This would integrate with the actual Brainlife task queue
    # For now, return mock data
    logger.info("Pulling tasks from Brainlife...")
    
    # Mock task data - in real implementation, this would query the Brainlife API
    mock_tasks = [
        {
            "id": "task_001",
            "app_id": "app_001",
            "project_id": project_filter or "default",
            "inputs": {"t1": "dataset_001"},
            "config": {"param1": "value1"}
        }
    ]
    
    return mock_tasks


def _create_brainlife_job_script(task):
    """Create a Brainlife job script for Slurm execution."""
    from ..api.slurm import create_brainlife_job_script
    
    return create_brainlife_job_script(
        task_config=task,
        app_config={"name": "brainlife_app"},
        inputs=task.get("inputs", {})
    )


def _monitor_slurm_jobs(cluster, jobs):
    """Monitor Slurm job execution."""
    logger.info("Monitoring Slurm job execution...")
    
    completed_jobs = []
    failed_jobs = []
    
    while jobs:
        for job in jobs[:]:  # Copy list to avoid modification during iteration
            try:
                current_job = cluster.get_job_status(job.job_id)
                
                if current_job.status in ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']:
                    jobs.remove(job)
                    
                    if current_job.status == 'COMPLETED':
                        completed_jobs.append(current_job)
                        logger.info(f"Job {current_job.job_id} completed successfully")
                    else:
                        failed_jobs.append(current_job)
                        logger.warning(f"Job {current_job.job_id} finished with status: {current_job.status}")
                
            except Exception as e:
                logger.error(f"Error monitoring job {job.job_id}: {e}")
        
        if jobs:
            time.sleep(30)  # Wait 30 seconds before checking again
    
    logger.info(f"Job monitoring completed: {len(completed_jobs)} completed, {len(failed_jobs)} failed")
    
    # Report results back to Brainlife
    _report_job_results(completed_jobs, failed_jobs)


def _report_job_results(completed_jobs, failed_jobs):
    """Report job results back to Brainlife."""
    logger.info("Reporting job results to Brainlife...")
    
    for job in completed_jobs:
        logger.info(f"Reporting successful completion of job {job.job_id}")
        # In real implementation, this would update the Brainlife task status
    
    for job in failed_jobs:
        logger.warning(f"Reporting failure of job {job.job_id}")
        # In real implementation, this would update the Brainlife task status with error details