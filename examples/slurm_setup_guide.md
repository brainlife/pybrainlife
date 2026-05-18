# Slurm Cluster Integration Setup Guide

This guide explains how to set up and use Slurm cluster integration with Brainlife.

## Overview

The Slurm integration allows Brainlife to execute tasks on high-performance computing (HPC) clusters managed by the Slurm workload manager. This enables:

- Distributed task execution across multiple compute nodes
- Resource management and job scheduling
- Integration with existing HPC infrastructure
- Support for GPU and specialized hardware

## Prerequisites

### Cluster Access
- SSH access to the Slurm cluster login node
- Valid user account on the cluster
- SSH key authentication (recommended)

### Software Requirements
- Slurm workload manager installed on the cluster
- Singularity or Docker for container execution
- Python 3.8+ on the cluster
- Network access to Brainlife services

## Configuration

### 1. Resource Configuration

Create a Brainlife resource with Slurm configuration:

```json
{
  "name": "Slurm Cluster Resource",
  "config": {
    "slurm": {
      "partition": "compute",
      "nodes": 1,
      "cpus": 4,
      "memory": "8G",
      "time_limit": "02:00:00",
      "account": "your_account",
      "qos": "normal",
      "work_dir": "/scratch/brainlife",
      "output_dir": "/scratch/brainlife/outputs",
      "error_dir": "/scratch/brainlife/errors",
      "environment": {
        "MODULEPATH": "/opt/modules",
        "SINGULARITY_CACHEDIR": "/scratch/singularity_cache"
      }
    }
  },
  "envs": {
    "SLURM_CLUSTER": "main_cluster",
    "SLURM_PARTITION": "compute"
  }
}
```

### 2. SSH Configuration

Set up SSH key authentication:

```bash
# Generate SSH key pair
ssh-keygen -t rsa -b 4096 -f ~/.ssh/brainlife_slurm_key

# Copy public key to cluster
ssh-copy-id -i ~/.ssh/brainlife_slurm_key.pub username@login.cluster.edu

# Test connection
ssh -i ~/.ssh/brainlife_slurm_key username@login.cluster.edu
```

### 3. Environment Variables

Set up environment variables for cluster access:

```bash
export SLURM_HOST="login.cluster.edu"
export SLURM_USER="your_username"
export SLURM_SSH_KEY="~/.ssh/brainlife_slurm_key"
export SLURM_WORK_DIR="/scratch/brainlife"
```

## Usage

### Command Line Interface

#### Check Cluster Status
```bash
bl resource slurm status --host login.cluster.edu --user myuser
```

#### View Job Queue
```bash
bl resource slurm queue --host login.cluster.edu --user myuser
```

#### Submit a Job
```bash
bl resource slurm submit job.sh \
  --name my_job \
  --partition compute \
  --cpus 4 \
  --memory 8G \
  --time 01:00:00 \
  --account my_account
```

#### Cancel a Job
```bash
bl resource slurm cancel 12345 --host login.cluster.edu --user myuser
```

### Brainlife Integration

#### Execute Tasks with Slurm
```bash
# Pull and execute tasks using Slurm
bl resource pull --slurm \
  --slurm-host login.cluster.edu \
  --slurm-user myuser \
  --project my_project

# Use specific resource configuration
bl resource pull --slurm \
  --slurm-host login.cluster.edu \
  --slurm-user myuser \
  --resource slurm_resource_id
```

## Job Templates

### Basic Job Template
```bash
#!/bin/bash
#SBATCH --job-name=brainlife_task
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --account=your_account

# Load modules
module load singularity
module load python/3.8

# Set up environment
export BRAINLIFE_TASK_ID=${SLURM_JOB_ID}
export BRAINLIFE_WORK_DIR=${SLURM_SUBMIT_DIR}

# Create working directories
mkdir -p ${BRAINLIFE_WORK_DIR}/data
mkdir -p ${BRAINLIFE_WORK_DIR}/output

# Download input data
echo "Downloading input data..."
# Add data download logic here

# Run the application
echo "Running application..."
# Add app execution logic here

# Upload results
echo "Uploading results..."
# Add result upload logic here

echo "Task completed successfully"
```

### GPU Job Template
```bash
#!/bin/bash
#SBATCH --job-name=brainlife_gpu_task
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --gres=gpu:1
#SBATCH --account=your_account

# Load modules
module load singularity
module load python/3.8
module load cuda/11.0

# Set up environment
export BRAINLIFE_TASK_ID=${SLURM_JOB_ID}
export BRAINLIFE_WORK_DIR=${SLURM_SUBMIT_DIR}
export CUDA_VISIBLE_DEVICES=${SLURM_LOCALID}

# Create working directories
mkdir -p ${BRAINLIFE_WORK_DIR}/data
mkdir -p ${BRAINLIFE_WORK_DIR}/output

# Download input data
echo "Downloading input data..."
# Add data download logic here

# Run the GPU application
echo "Running GPU application..."
# Add GPU app execution logic here

# Upload results
echo "Uploading results..."
# Add result upload logic here

echo "GPU task completed successfully"
```

### Array Job Template
```bash
#!/bin/bash
#SBATCH --job-name=brainlife_array_task
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --array=1-10
#SBATCH --account=your_account

# Load modules
module load singularity
module load python/3.8

# Set up environment
export BRAINLIFE_TASK_ID=${SLURM_JOB_ID}_${SLURM_ARRAY_TASK_ID}
export BRAINLIFE_WORK_DIR=${SLURM_SUBMIT_DIR}/task_${SLURM_ARRAY_TASK_ID}

# Create working directories
mkdir -p ${BRAINLIFE_WORK_DIR}/data
mkdir -p ${BRAINLIFE_WORK_DIR}/output

# Download input data for this array task
echo "Downloading input data for task ${SLURM_ARRAY_TASK_ID}..."
# Add array-specific data download logic here

# Run the application
echo "Running application for task ${SLURM_ARRAY_TASK_ID}..."
# Add array-specific app execution logic here

# Upload results
echo "Uploading results for task ${SLURM_ARRAY_TASK_ID}..."
# Add array-specific result upload logic here

echo "Array task ${SLURM_ARRAY_TASK_ID} completed successfully"
```

## Advanced Configuration

### Resource Constraints
```json
{
  "slurm": {
    "constraint": "skylake",
    "features": "gpu",
    "gres": "gpu:1"
  }
}
```

### Quality of Service (QOS)
```json
{
  "slurm": {
    "qos": "high_priority",
    "account": "research_account"
  }
}
```

### Mail Notifications
```json
{
  "slurm": {
    "mail_type": "END,FAIL",
    "mail_user": "your_email@domain.com"
  }
}
```

### Environment Variables
```json
{
  "slurm": {
    "environment": {
      "MODULEPATH": "/opt/modules",
      "SINGULARITY_CACHEDIR": "/scratch/singularity_cache",
      "TMPDIR": "/scratch/tmp",
      "PYTHONPATH": "/opt/python/lib"
    }
  }
}
```

## Troubleshooting

### Common Issues

#### Connection Problems
```bash
# Test SSH connection
ssh -i ~/.ssh/brainlife_slurm_key username@login.cluster.edu

# Check SSH key permissions
chmod 600 ~/.ssh/brainlife_slurm_key
```

#### Job Submission Failures
```bash
# Check cluster status
bl resource slurm status --host login.cluster.edu --user myuser

# Verify partition availability
sinfo -p compute

# Check account permissions
sacctmgr show user username
```

#### Resource Allocation Issues
```bash
# Check available resources
sinfo -N -l

# Check partition limits
scontrol show partition compute

# Check account limits
sacctmgr show account your_account
```

### Debugging

#### Enable Verbose Logging
```bash
export PYBRAINLIFE_LOG_LEVEL=DEBUG
bl resource pull --slurm --slurm-host login.cluster.edu --slurm-user myuser
```

#### Check Job Logs
```bash
# View job output
cat /scratch/brainlife/outputs/brainlife_12345.out

# View job errors
cat /scratch/brainlife/errors/brainlife_12345.err

# Check job status
scontrol show job 12345
```

## Best Practices

### Resource Management
- Use appropriate partition and QOS settings
- Set realistic time limits to avoid job cancellation
- Monitor resource usage and adjust allocations

### Security
- Use SSH key authentication
- Restrict SSH key permissions
- Regularly rotate SSH keys

### Performance
- Use local storage for temporary files
- Optimize data transfer between cluster and Brainlife
- Monitor job queue and adjust submission timing

### Monitoring
- Set up mail notifications for job completion
- Monitor cluster status regularly
- Track resource usage and costs

## Support

For additional support with Slurm integration:

1. Check the Brainlife documentation
2. Contact your cluster administrator
3. Review Slurm documentation
4. Submit issues to the pybrainlife repository

