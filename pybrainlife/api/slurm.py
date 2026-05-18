"""
Slurm cluster integration for Brainlife task execution.

This module provides functionality to interact with Slurm clusters for
distributed task execution in the Brainlife platform.
"""

import json
import subprocess
import tempfile
import os
import time
import logging
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("pybrainlife.slurm")


@dataclass
class SlurmJob:
    """Represents a Slurm job."""
    job_id: str
    name: str
    status: str
    partition: str
    nodes: int
    cpus: int
    memory: str
    time_limit: str
    submit_time: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    exit_code: Optional[int] = None
    output_file: Optional[str] = None
    error_file: Optional[str] = None


@dataclass
class SlurmConfig:
    """Configuration for Slurm job submission."""
    partition: str = "default"
    nodes: int = 1
    cpus: int = 1
    memory: str = "1G"
    time_limit: str = "01:00:00"
    account: Optional[str] = None
    qos: Optional[str] = None
    constraint: Optional[str] = None
    features: Optional[str] = None
    gres: Optional[str] = None
    mail_type: Optional[str] = None
    mail_user: Optional[str] = None
    work_dir: Optional[str] = None
    output_dir: Optional[str] = None
    error_dir: Optional[str] = None
    dependencies: Optional[List[str]] = None
    array_indices: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)


class SlurmCluster:
    """Interface for interacting with a Slurm cluster."""
    
    def __init__(self, 
                 hostname: Optional[str] = None,
                 username: Optional[str] = None,
                 ssh_key: Optional[str] = None,
                 work_dir: str = "/tmp/brainlife"):
        """
        Initialize Slurm cluster connection.
        
        Args:
            hostname: SSH hostname for the cluster login node
            username: SSH username for cluster access
            ssh_key: Path to SSH private key file
            work_dir: Working directory on the cluster
        """
        self.hostname = hostname
        self.username = username
        self.ssh_key = ssh_key
        self.work_dir = work_dir
        self._connection_test()
    
    def _connection_test(self):
        """Test connection to the Slurm cluster."""
        if not self.hostname:
            logger.warning("No hostname provided, using local Slurm commands")
            return
        
        try:
            cmd = self._build_ssh_command(["sinfo", "--version"])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"Successfully connected to Slurm cluster at {self.hostname}")
            else:
                logger.warning(f"Could not connect to Slurm cluster: {result.stderr}")
        except Exception as e:
            logger.warning(f"Slurm cluster connection test failed: {e}")
    
    def _build_ssh_command(self, command: List[str]) -> List[str]:
        """Build SSH command for remote execution."""
        if not self.hostname:
            return command
        
        ssh_cmd = ["ssh"]
        if self.username:
            ssh_cmd.extend(["-l", self.username])
        if self.ssh_key:
            ssh_cmd.extend(["-i", self.ssh_key])
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=no"])
        ssh_cmd.append(self.hostname)
        ssh_cmd.extend(command)
        return ssh_cmd
    
    def submit_job(self, 
                   script_content: str,
                   job_name: str,
                   config: SlurmConfig,
                   wait: bool = False) -> SlurmJob:
        """
        Submit a job to the Slurm cluster.
        
        Args:
            script_content: The job script content
            job_name: Name for the job
            config: Slurm configuration
            wait: Whether to wait for job completion
            
        Returns:
            SlurmJob object with job details
        """
        # Create job script
        script_path = self._create_job_script(script_content, job_name, config)
        
        # Submit job
        submit_cmd = ["sbatch", "--parsable", script_path]
        submit_cmd.extend(self._build_sbatch_args(config))
        
        try:
            cmd = self._build_ssh_command(submit_cmd)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                raise Exception(f"Job submission failed: {result.stderr}")
            
            job_id = result.stdout.strip()
            logger.info(f"Job {job_name} submitted with ID: {job_id}")
            
            # Get job details
            job = self.get_job_status(job_id)
            
            if wait:
                job = self.wait_for_job(job_id)
            
            return job
            
        except Exception as e:
            logger.error(f"Failed to submit job {job_name}: {e}")
            raise
    
    def _create_job_script(self, content: str, job_name: str, config: SlurmConfig) -> str:
        """Create a Slurm job script file."""
        script_lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name={job_name}",
            f"#SBATCH --partition={config.partition}",
            f"#SBATCH --nodes={config.nodes}",
            f"#SBATCH --cpus-per-task={config.cpus}",
            f"#SBATCH --mem={config.memory}",
            f"#SBATCH --time={config.time_limit}",
        ]
        
        if config.account:
            script_lines.append(f"#SBATCH --account={config.account}")
        if config.qos:
            script_lines.append(f"#SBATCH --qos={config.qos}")
        if config.constraint:
            script_lines.append(f"#SBATCH --constraint={config.constraint}")
        if config.features:
            script_lines.append(f"#SBATCH --features={config.features}")
        if config.gres:
            script_lines.append(f"#SBATCH --gres={config.gres}")
        if config.mail_type:
            script_lines.append(f"#SBATCH --mail-type={config.mail_type}")
        if config.mail_user:
            script_lines.append(f"#SBATCH --mail-user={config.mail_user}")
        if config.array_indices:
            script_lines.append(f"#SBATCH --array={config.array_indices}")
        
        # Set output and error files
        output_dir = config.output_dir or config.work_dir or "/tmp"
        error_dir = config.error_dir or config.work_dir or "/tmp"
        script_lines.extend([
            f"#SBATCH --output={output_dir}/{job_name}_%j.out",
            f"#SBATCH --error={error_dir}/{job_name}_%j.err",
        ])
        
        # Set working directory
        work_dir = config.work_dir or "/tmp"
        script_lines.append(f"#SBATCH --chdir={work_dir}")
        
        # Add environment variables
        for key, value in config.environment.items():
            script_lines.append(f"export {key}={value}")
        
        # Add job dependencies
        if config.dependencies:
            deps = ":".join(config.dependencies)
            script_lines.append(f"#SBATCH --dependency=afterok:{deps}")
        
        script_lines.append("")  # Empty line
        script_lines.append(content)
        
        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write('\n'.join(script_lines))
            return f.name
    
    def _build_sbatch_args(self, config: SlurmConfig) -> List[str]:
        """Build sbatch command line arguments."""
        args = []
        
        if config.account:
            args.extend(["--account", config.account])
        if config.qos:
            args.extend(["--qos", config.qos])
        if config.constraint:
            args.extend(["--constraint", config.constraint])
        if config.features:
            args.extend(["--features", config.features])
        if config.gres:
            args.extend(["--gres", config.gres])
        if config.mail_type:
            args.extend(["--mail-type", config.mail_type])
        if config.mail_user:
            args.extend(["--mail-user", config.mail_user])
        if config.array_indices:
            args.extend(["--array", config.array_indices])
        
        return args
    
    def get_job_status(self, job_id: str) -> SlurmJob:
        """Get the status of a specific job."""
        cmd = self._build_ssh_command([
            "scontrol", "show", "job", job_id
        ])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise Exception(f"Failed to get job status: {result.stderr}")
            
            return self._parse_job_info(result.stdout, job_id)
            
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            raise
    
    def _parse_job_info(self, scontrol_output: str, job_id: str) -> SlurmJob:
        """Parse scontrol output to extract job information."""
        lines = scontrol_output.strip().split('\n')
        job_info = {}
        
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                job_info[key.strip()] = value.strip()
        
        return SlurmJob(
            job_id=job_id,
            name=job_info.get('JobName', 'unknown'),
            status=job_info.get('JobState', 'unknown'),
            partition=job_info.get('Partition', 'unknown'),
            nodes=int(job_info.get('NumNodes', 1)),
            cpus=int(job_info.get('NumCPUs', 1)),
            memory=job_info.get('MinMemoryCPU', 'unknown'),
            time_limit=job_info.get('TimeLimit', 'unknown'),
            submit_time=job_info.get('SubmitTime', 'unknown'),
            start_time=job_info.get('StartTime', None),
            end_time=job_info.get('EndTime', None),
            exit_code=job_info.get('ExitCode', None),
            output_file=job_info.get('StdOut', None),
            error_file=job_info.get('StdErr', None)
        )
    
    def wait_for_job(self, job_id: str, poll_interval: int = 30) -> SlurmJob:
        """Wait for a job to complete."""
        logger.info(f"Waiting for job {job_id} to complete...")
        
        while True:
            job = self.get_job_status(job_id)
            
            if job.status in ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT']:
                logger.info(f"Job {job_id} finished with status: {job.status}")
                return job
            
            logger.debug(f"Job {job_id} status: {job.status}")
            time.sleep(poll_interval)
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        cmd = self._build_ssh_command(["scancel", job_id])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"Job {job_id} cancelled successfully")
                return True
            else:
                logger.error(f"Failed to cancel job {job_id}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error cancelling job {job_id}: {e}")
            return False
    
    def get_queue_status(self) -> List[SlurmJob]:
        """Get status of all jobs in the queue."""
        cmd = self._build_ssh_command([
            "squeue", "--format=%i,%j,%T,%P,%D,%C,%m,%l,%S,%e,%V", "--noheader"
        ])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise Exception(f"Failed to get queue status: {result.stderr}")
            
            jobs = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 11:
                        jobs.append(SlurmJob(
                            job_id=parts[0],
                            name=parts[1],
                            status=parts[2],
                            partition=parts[3],
                            nodes=int(parts[4]) if parts[4] else 1,
                            cpus=int(parts[5]) if parts[5] else 1,
                            memory=parts[6],
                            time_limit=parts[7],
                            submit_time=parts[8],
                            start_time=parts[9] if parts[9] != 'N/A' else None,
                            end_time=parts[10] if parts[10] != 'N/A' else None
                        ))
            
            return jobs
            
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            raise
    
    def get_cluster_info(self) -> Dict[str, Any]:
        """Get information about the cluster."""
        cmd = self._build_ssh_command(["sinfo", "--format=%P,%A,%T,%N,%G"])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise Exception(f"Failed to get cluster info: {result.stderr}")
            
            partitions = {}
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            
            for line in lines:
                if line.strip():
                    parts = line.split(',')
                    if len(parts) >= 5:
                        partition = parts[0]
                        partitions[partition] = {
                            'available': parts[1],
                            'state': parts[2],
                            'nodes': parts[3],
                            'gres': parts[4]
                        }
            
            return {
                'partitions': partitions,
                'hostname': self.hostname,
                'username': self.username
            }
            
        except Exception as e:
            logger.error(f"Failed to get cluster info: {e}")
            raise


def create_slurm_config_from_resource(resource_config: Dict[str, Any]) -> SlurmConfig:
    """
    Create a SlurmConfig from a Brainlife resource configuration.
    
    Args:
        resource_config: Resource configuration dictionary
        
    Returns:
        SlurmConfig object
    """
    config = SlurmConfig()
    
    # Map resource config to Slurm config
    if 'slurm' in resource_config:
        slurm_config = resource_config['slurm']
        
        config.partition = slurm_config.get('partition', 'default')
        config.nodes = slurm_config.get('nodes', 1)
        config.cpus = slurm_config.get('cpus', 1)
        config.memory = slurm_config.get('memory', '1G')
        config.time_limit = slurm_config.get('time_limit', '01:00:00')
        config.account = slurm_config.get('account')
        config.qos = slurm_config.get('qos')
        config.constraint = slurm_config.get('constraint')
        config.features = slurm_config.get('features')
        config.gres = slurm_config.get('gres')
        config.mail_type = slurm_config.get('mail_type')
        config.mail_user = slurm_config.get('mail_user')
        config.work_dir = slurm_config.get('work_dir')
        config.output_dir = slurm_config.get('output_dir')
        config.error_dir = slurm_config.get('error_dir')
        config.environment = slurm_config.get('environment', {})
    
    return config


def create_brainlife_job_script(task_config: Dict[str, Any], 
                               app_config: Dict[str, Any],
                               inputs: Dict[str, Any]) -> str:
    """
    Create a Brainlife job script for Slurm execution.
    
    Args:
        task_config: Task configuration
        app_config: Application configuration
        inputs: Input data configuration
        
    Returns:
        Job script content as string
    """
    script_lines = [
        "#!/bin/bash",
        "set -e",
        "",
        "# Brainlife task execution script",
        f"# Task ID: {task_config.get('task_id', 'unknown')}",
        f"# App: {app_config.get('name', 'unknown')}",
        "",
        "# Set up environment",
        "export BRAINLIFE_TASK_ID=${SLURM_JOB_ID}",
        "export BRAINLIFE_WORK_DIR=${SLURM_SUBMIT_DIR}",
        "",
        "# Create working directory",
        "mkdir -p ${BRAINLIFE_WORK_DIR}/data",
        "mkdir -p ${BRAINLIFE_WORK_DIR}/output",
        "",
        "# Download input data",
        "echo 'Downloading input data...'",
    ]
    
    # Add data download commands
    for field, dataset_id in inputs.items():
        script_lines.extend([
            f"echo 'Downloading {field}: {dataset_id}'",
            f"# Add data download logic for {field}",
        ])
    
    script_lines.extend([
        "",
        "# Run the application",
        "echo 'Running application...'",
        f"# Add app execution logic for {app_config.get('name', 'app')}",
        "",
        "# Upload results",
        "echo 'Uploading results...'",
        "# Add result upload logic",
        "",
        "echo 'Task completed successfully'",
    ])
    
    return '\n'.join(script_lines)

