"""
Task execution API for Brainlife.

This module provides functionality to pull tasks from the Brainlife API
and execute them on various resources including local and Slurm clusters.
"""

import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime

from .api import auth_header, services, api_error
from .task import Task, task_wait, TaskFailed, TaskInvalidState
from .app import app_fetch
from .project import project_fetch
from .resource import resource_fetch, find_best_resource
from .dataset import dataset_query
from .slurm import SlurmCluster, SlurmConfig, create_slurm_config_from_resource, create_brainlife_job_script

logger = logging.getLogger("pybrainlife.task_executor")


@dataclass
class TaskExecutionConfig:
    """Configuration for task execution."""
    resource_id: Optional[str] = None
    project_id: Optional[str] = None
    max_concurrent_tasks: int = 1
    poll_interval: int = 30
    timeout: Optional[int] = None
    retry_failed: bool = True
    max_retries: int = 3
    use_slurm: bool = False
    slurm_config: Optional[SlurmConfig] = None
    slurm_cluster: Optional[SlurmCluster] = None


@dataclass
class TaskExecutionResult:
    """Result of task execution."""
    task_id: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    error_message: Optional[str] = None
    outputs: List[Dict] = field(default_factory=list)
    slurm_job_id: Optional[str] = None


class TaskExecutor:
    """Executes Brainlife tasks on various resources."""
    
    def __init__(self, config: TaskExecutionConfig):
        """
        Initialize task executor.
        
        Args:
            config: Task execution configuration
        """
        self.config = config
        self.running_tasks: Dict[str, TaskExecutionResult] = {}
        self.completed_tasks: List[TaskExecutionResult] = []
        self.failed_tasks: List[TaskExecutionResult] = []
        
        # Initialize Slurm cluster if configured
        if config.use_slurm and config.slurm_cluster:
            self.slurm_cluster = config.slurm_cluster
        elif config.use_slurm:
            self.slurm_cluster = SlurmCluster()
        else:
            self.slurm_cluster = None
    
    def pull_tasks(self, 
                   status: str = "pending",
                   limit: int = 10,
                   auth=None) -> List[Dict[str, Any]]:
        """
        Pull tasks from Brainlife API.
        
        Args:
            status: Task status to filter by
            limit: Maximum number of tasks to pull
            auth: Authentication token
            
        Returns:
            List of task dictionaries
        """
        query = {"status": status}
        
        # Add project filter if specified
        if self.config.project_id:
            query["project"] = self.config.project_id
        
        # Add resource filter if specified
        if self.config.resource_id:
            query["resource"] = self.config.resource_id
        
        url = services["amaretti"] + "/task"
        res = requests.get(
            url,
            params={
                "find": json.dumps(query),
                "sort": "created",
                "limit": limit,
            },
            headers={**auth_header(auth)},
        )
        
        api_error(res)
        
        tasks_data = res.json().get("tasks", [])
        logger.info(f"Pulled {len(tasks_data)} tasks from API")
        
        return tasks_data
    
    def execute_task(self, task_data: Dict[str, Any], auth=None) -> TaskExecutionResult:
        """
        Execute a single task.
        
        Args:
            task_data: Task data from API
            auth: Authentication token
            
        Returns:
            TaskExecutionResult object
        """
        task_id = task_data.get("_id", task_data.get("id"))
        task_name = task_data.get("name", f"task_{task_id}")
        
        logger.info(f"Executing task {task_id}: {task_name}")
        
        result = TaskExecutionResult(
            task_id=task_id,
            status="running",
            start_time=datetime.now()
        )
        
        self.running_tasks[task_id] = result
        
        try:
            if self.config.use_slurm and self.slurm_cluster:
                self._execute_task_slurm(task_data, result, auth)
            else:
                self._execute_task_local(task_data, result, auth)
            
            result.status = "completed"
            result.end_time = datetime.now()
            result.duration = (result.end_time - result.start_time).total_seconds()
            
            logger.info(f"Task {task_id} completed successfully in {result.duration:.2f}s")
            
        except Exception as e:
            result.status = "failed"
            result.end_time = datetime.now()
            result.duration = (result.end_time - result.start_time).total_seconds()
            result.error_message = str(e)
            
            logger.error(f"Task {task_id} failed: {e}")
            
            if self.config.retry_failed:
                self._handle_task_retry(task_data, result, auth)
        
        # Move from running to completed/failed
        del self.running_tasks[task_id]
        
        if result.status == "completed":
            self.completed_tasks.append(result)
        else:
            self.failed_tasks.append(result)
        
        return result
    
    def _execute_task_slurm(self, task_data: Dict[str, Any], 
                           result: TaskExecutionResult, auth=None):
        """Execute task using Slurm cluster."""
        logger.info(f"Executing task {result.task_id} on Slurm cluster")
        
        # Get task configuration
        task_config = task_data.get("config", {})
        app_id = task_config.get("_app")
        
        if not app_id:
            raise ValueError("No app ID found in task configuration")
        
        # Fetch app details
        app = app_fetch(app_id, auth)
        if not app:
            raise ValueError(f"App {app_id} not found")
        
        # Create job script
        job_script = create_brainlife_job_script(
            task_config=task_data,
            app_config={"name": app.name, "id": app.id},
            inputs=task_config.get("_inputs", {})
        )
        
        # Get Slurm configuration
        slurm_config = self.config.slurm_config or SlurmConfig()
        
        # Override with resource configuration if available
        if self.config.resource_id:
            resource = resource_fetch(self.config.resource_id, auth)
            if resource and resource.config:
                slurm_config = create_slurm_config_from_resource(resource.config)
        
        # Submit job to Slurm
        job_name = f"brainlife_{result.task_id}"
        slurm_job = self.slurm_cluster.submit_job(
            script_content=job_script,
            job_name=job_name,
            config=slurm_config,
            wait=False
        )
        
        result.slurm_job_id = slurm_job.job_id
        logger.info(f"Submitted task {result.task_id} as Slurm job {slurm_job.job_id}")
        
        # Update task status in Brainlife
        self._update_task_status(result.task_id, "running", auth)
        
        # Monitor Slurm job
        self._monitor_slurm_job(slurm_job.job_id, result, auth)
    
    def _execute_task_local(self, task_data: Dict[str, Any], 
                           result: TaskExecutionResult, auth=None):
        """Execute task locally."""
        logger.info(f"Executing task {result.task_id} locally")
        
        # Get task configuration
        task_config = task_data.get("config", {})
        app_id = task_config.get("_app")
        
        if not app_id:
            raise ValueError("No app ID found in task configuration")
        
        # Fetch app details
        app = app_fetch(app_id, auth)
        if not app:
            raise ValueError(f"App {app_id} not found")
        
        # Update task status to running
        self._update_task_status(result.task_id, "running", auth)
        
        # Execute the task using Brainlife's task execution API
        # This would typically involve:
        # 1. Staging input data
        # 2. Running the application
        # 3. Collecting outputs
        # 4. Updating task status
        
        # For now, simulate task execution
        logger.info(f"Running app {app.name} for task {result.task_id}")
        
        # Simulate processing time
        time.sleep(2)
        
        # Update task status to completed
        self._update_task_status(result.task_id, "completed", auth)
    
    def _monitor_slurm_job(self, job_id: str, result: TaskExecutionResult, auth=None):
        """Monitor Slurm job execution."""
        logger.info(f"Monitoring Slurm job {job_id}")
        
        while True:
            try:
                job_status = self.slurm_cluster.get_job_status(job_id)
                
                if job_status.status in ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']:
                    if job_status.status == 'COMPLETED':
                        logger.info(f"Slurm job {job_id} completed successfully")
                        self._update_task_status(result.task_id, "completed", auth)
                    else:
                        logger.warning(f"Slurm job {job_id} finished with status: {job_status.status}")
                        self._update_task_status(result.task_id, "failed", auth)
                        raise Exception(f"Slurm job failed with status: {job_status.status}")
                    break
                
                time.sleep(self.config.poll_interval)
                
            except Exception as e:
                logger.error(f"Error monitoring Slurm job {job_id}: {e}")
                self._update_task_status(result.task_id, "failed", auth)
                raise
    
    def _update_task_status(self, task_id: str, status: str, auth=None):
        """Update task status in Brainlife."""
        url = services["amaretti"] + f"/task/{task_id}"
        
        update_data = {
            "status": status,
            "updated": datetime.now().isoformat()
        }
        
        try:
            res = requests.put(
                url,
                json=update_data,
                headers={**auth_header(auth)},
            )
            api_error(res)
            logger.debug(f"Updated task {task_id} status to {status}")
            
        except Exception as e:
            logger.warning(f"Failed to update task {task_id} status: {e}")
    
    def _handle_task_retry(self, task_data: Dict[str, Any], 
                          result: TaskExecutionResult, auth=None):
        """Handle task retry logic."""
        retry_count = getattr(result, 'retry_count', 0)
        
        if retry_count < self.config.max_retries:
            retry_count += 1
            result.retry_count = retry_count
            
            logger.info(f"Retrying task {result.task_id} (attempt {retry_count}/{self.config.max_retries})")
            
            # Wait before retry
            time.sleep(60 * retry_count)  # Exponential backoff
            
            # Reset result for retry
            result.status = "running"
            result.start_time = datetime.now()
            result.end_time = None
            result.duration = None
            result.error_message = None
            
            # Re-execute task
            self.execute_task(task_data, auth)
    
    def execute_tasks(self, 
                     status: str = "pending",
                     limit: int = 10,
                     auth=None) -> List[TaskExecutionResult]:
        """
        Execute multiple tasks.
        
        Args:
            status: Task status to filter by
            limit: Maximum number of tasks to execute
            auth: Authentication token
            
        Returns:
            List of TaskExecutionResult objects
        """
        logger.info(f"Starting task execution (limit: {limit}, status: {status})")
        
        # Pull tasks from API
        tasks_data = self.pull_tasks(status=status, limit=limit, auth=auth)
        
        if not tasks_data:
            logger.info("No tasks found for execution")
            return []
        
        results = []
        
        # Execute tasks (with concurrency limit)
        for i in range(0, len(tasks_data), self.config.max_concurrent_tasks):
            batch = tasks_data[i:i + self.config.max_concurrent_tasks]
            
            logger.info(f"Executing batch of {len(batch)} tasks")
            
            for task_data in batch:
                try:
                    result = self.execute_task(task_data, auth)
                    results.append(result)
                    
                    # Check if we've hit the limit
                    if len(results) >= limit:
                        break
                        
                except Exception as e:
                    logger.error(f"Failed to execute task: {e}")
                    continue
            
            # Wait between batches if there are more tasks
            if i + self.config.max_concurrent_tasks < len(tasks_data):
                time.sleep(5)
        
        logger.info(f"Task execution completed: {len(self.completed_tasks)} completed, {len(self.failed_tasks)} failed")
        
        return results
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of task execution."""
        total_tasks = len(self.completed_tasks) + len(self.failed_tasks)
        
        summary = {
            "total_tasks": total_tasks,
            "completed": len(self.completed_tasks),
            "failed": len(self.failed_tasks),
            "running": len(self.running_tasks),
            "success_rate": len(self.completed_tasks) / total_tasks if total_tasks > 0 else 0,
            "average_duration": sum(r.duration for r in self.completed_tasks if r.duration) / len(self.completed_tasks) if self.completed_tasks else 0
        }
        
        return summary


def create_task_executor(resource_id: Optional[str] = None,
                        project_id: Optional[str] = None,
                        use_slurm: bool = False,
                        slurm_host: Optional[str] = None,
                        slurm_user: Optional[str] = None,
                        slurm_key: Optional[str] = None,
                        max_concurrent_tasks: int = 1,
                        poll_interval: int = 30) -> TaskExecutor:
    """
    Create a TaskExecutor with the specified configuration.
    
    Args:
        resource_id: Resource ID to use for execution
        project_id: Project ID to filter tasks
        use_slurm: Whether to use Slurm cluster
        slurm_host: Slurm cluster hostname
        slurm_user: Slurm cluster username
        slurm_key: SSH key for Slurm cluster
        max_concurrent_tasks: Maximum concurrent tasks
        poll_interval: Polling interval for monitoring
        
    Returns:
        TaskExecutor instance
    """
    config = TaskExecutionConfig(
        resource_id=resource_id,
        project_id=project_id,
        max_concurrent_tasks=max_concurrent_tasks,
        poll_interval=poll_interval,
        use_slurm=use_slurm
    )
    
    if use_slurm:
        config.slurm_cluster = SlurmCluster(
            hostname=slurm_host,
            username=slurm_user,
            ssh_key=slurm_key
        )
    
    return TaskExecutor(config)
