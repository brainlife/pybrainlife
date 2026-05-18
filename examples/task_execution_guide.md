# Task Execution CLI Guide

This guide explains how to use the Brainlife task execution CLI to pull and execute tasks from the Brainlife API.

## Overview

The task execution CLI provides comprehensive functionality for:

- Pulling tasks from the Brainlife API
- Executing tasks locally or on Slurm clusters
- Monitoring task execution in real-time
- Managing task results and error handling
- Integration with Brainlife resources and projects

## Prerequisites

### Authentication
- Valid Brainlife account and authentication token
- Proper authentication setup using `bl login`

### Resources
- Access to Brainlife resources (local or Slurm clusters)
- Proper resource configuration for task execution

## Basic Usage

### Execute Tasks

The primary command for task execution is `bl task execute`:

```bash
# Basic task execution
bl task execute

# Execute tasks with specific parameters
bl task execute --limit 5 --status pending --max-concurrent 2

# Execute tasks for a specific project
bl task execute --project project_id --limit 10

# Execute tasks using a specific resource
bl task execute --resource resource_id --limit 5
```

### List Tasks

View available tasks without executing them:

```bash
# List all pending tasks
bl task list --status pending

# List tasks for a specific project
bl task list --project project_id --limit 20

# List tasks in JSON format
bl task list --format json --limit 10
```

### Monitor Tasks

Monitor running tasks in real-time:

```bash
# Monitor all running tasks
bl task monitor

# Monitor tasks for a specific project
bl task monitor --project project_id --interval 30

# Monitor for a specific duration
bl task monitor --duration 3600 --interval 60
```

## Advanced Configuration

### Slurm Integration

Execute tasks on Slurm clusters:

```bash
# Execute tasks using Slurm
bl task execute --slurm --slurm-host login.cluster.edu --slurm-user myuser

# Execute with Slurm-specific configuration
bl task execute --slurm \
  --slurm-host login.cluster.edu \
  --slurm-user myuser \
  --slurm-key ~/.ssh/slurm_key \
  --max-concurrent 5
```

### Resource Management

Configure task execution resources:

```bash
# Use specific resource
bl task execute --resource resource_id

# Execute with resource limits
bl task execute --resource resource_id --max-concurrent 3 --poll-interval 20
```

### Project Filtering

Filter tasks by project:

```bash
# Execute tasks from specific project
bl task execute --project project_id --limit 10

# List tasks from specific project
bl task list --project project_id --status pending
```

## Command Reference

### `bl task execute`

Execute tasks from the Brainlife API.

#### Options

- `-r, --resource`: Resource ID to use for execution
- `-p, --project`: Project ID to filter tasks
- `-l, --limit`: Maximum number of tasks to execute (default: 10)
- `-s, --status`: Task status to filter by (default: pending)
- `--max-concurrent`: Maximum concurrent tasks (default: 1)
- `--poll-interval`: Polling interval in seconds (default: 30)
- `--timeout`: Timeout in seconds for task execution
- `--no-retry`: Disable automatic retry of failed tasks
- `--max-retries`: Maximum number of retries for failed tasks (default: 3)

#### Slurm Options

- `--slurm`: Use Slurm cluster for task execution
- `--slurm-host`: Slurm cluster hostname
- `--slurm-user`: Slurm cluster username
- `--slurm-key`: SSH key for Slurm cluster access

#### Output Options

- `--output`: Output file for execution results (JSON format)
- `--verbose`: Verbose output

#### Examples

```bash
# Basic execution
bl task execute

# Execute with custom limits
bl task execute --limit 20 --max-concurrent 3

# Execute with Slurm
bl task execute --slurm --slurm-host cluster.edu --slurm-user myuser

# Execute with output file
bl task execute --output results.json --verbose

# Execute with retry configuration
bl task execute --max-retries 5 --no-retry
```

### `bl task list`

List tasks from the Brainlife API.

#### Options

- `-p, --project`: Project ID to filter tasks
- `-r, --resource`: Resource ID to filter tasks
- `-s, --status`: Task status to filter by
- `-l, --limit`: Maximum number of tasks to list (default: 20)
- `--format`: Output format (table, json) (default: table)

#### Examples

```bash
# List pending tasks
bl task list --status pending

# List tasks in JSON format
bl task list --format json --limit 50

# List tasks for specific project
bl task list --project project_id --status running
```

### `bl task monitor`

Monitor running tasks in real-time.

#### Options

- `-p, --project`: Project ID to filter tasks
- `-r, --resource`: Resource ID to filter tasks
- `--interval`: Monitoring interval in seconds (default: 30)
- `--duration`: Monitoring duration in seconds (default: indefinite)

#### Examples

```bash
# Monitor all running tasks
bl task monitor

# Monitor with custom interval
bl task monitor --interval 60

# Monitor for specific duration
bl task monitor --duration 1800 --interval 30

# Monitor specific project
bl task monitor --project project_id --interval 20
```

### `bl task status`

Get task execution status and summary.

#### Options

- `--format`: Output format (table, json) (default: table)

#### Examples

```bash
# Get status summary
bl task status

# Get status in JSON format
bl task status --format json
```

## Configuration Examples

### Basic Configuration

```bash
# Execute 5 tasks with 2 concurrent executions
bl task execute --limit 5 --max-concurrent 2

# Execute tasks with custom polling
bl task execute --poll-interval 15 --timeout 1800

# Execute with retry configuration
bl task execute --max-retries 3 --no-retry
```

### Slurm Configuration

```bash
# Basic Slurm execution
bl task execute --slurm --slurm-host login.cluster.edu --slurm-user myuser

# Slurm with SSH key
bl task execute --slurm \
  --slurm-host login.cluster.edu \
  --slurm-user myuser \
  --slurm-key ~/.ssh/slurm_key

# Slurm with resource limits
bl task execute --slurm \
  --slurm-host login.cluster.edu \
  --slurm-user myuser \
  --max-concurrent 5 \
  --poll-interval 60
```

### Project-Specific Execution

```bash
# Execute tasks from specific project
bl task execute --project 507f1f77bcf86cd799439011 --limit 10

# Monitor tasks from specific project
bl task monitor --project 507f1f77bcf86cd799439011 --interval 30

# List tasks from specific project
bl task list --project 507f1f77bcf86cd799439011 --status pending
```

### Resource-Specific Execution

```bash
# Execute tasks using specific resource
bl task execute --resource 507f1f77bcf86cd799439012 --limit 5

# Execute with resource and project filters
bl task execute \
  --resource 507f1f77bcf86cd799439012 \
  --project 507f1f77bcf86cd799439011 \
  --limit 10
```

## Output and Results

### Execution Summary

The CLI provides detailed execution summaries:

```
============================================================
TASK EXECUTION SUMMARY
============================================================
Total tasks: 10
Completed: 8
Failed: 2
Running: 0
Success rate: 80.0%
Average duration: 45.2s
============================================================
```

### Detailed Results

With verbose output (`--verbose`), detailed results are shown:

```
DETAILED RESULTS:
------------------------------------------------------------
✓ task_001: completed (42.3s)
✓ task_002: completed (38.7s)
✓ task_003: completed (45.1s)
✗ task_004: failed
  Error: Resource allocation failed
✗ task_005: failed
  Error: Application execution timeout
```

### JSON Output

Results can be saved to JSON files:

```bash
bl task execute --output results.json --verbose
```

Example JSON output:

```json
{
  "summary": {
    "total_tasks": 10,
    "completed": 8,
    "failed": 2,
    "running": 0,
    "success_rate": 0.8,
    "average_duration": 45.2
  },
  "completed_tasks": [
    {
      "task_id": "task_001",
      "status": "completed",
      "duration": 42.3,
      "start_time": "2024-01-15T10:30:00",
      "end_time": "2024-01-15T10:30:42",
      "slurm_job_id": "12345"
    }
  ],
  "failed_tasks": [
    {
      "task_id": "task_004",
      "status": "failed",
      "duration": 15.2,
      "start_time": "2024-01-15T10:35:00",
      "end_time": "2024-01-15T10:35:15",
      "error_message": "Resource allocation failed"
    }
  ]
}
```

## Error Handling

### Common Errors

#### Authentication Errors
```bash
# Error: Authentication required
# Solution: Run 'bl login' first
bl login
```

#### Resource Errors
```bash
# Error: Resource not found
# Solution: Check resource ID or create resource
bl resource list
```

#### Project Errors
```bash
# Error: Project not found
# Solution: Check project ID or permissions
bl project list
```

#### Slurm Errors
```bash
# Error: Slurm cluster connection failed
# Solution: Check SSH configuration and cluster access
ssh -i ~/.ssh/slurm_key user@login.cluster.edu
```

### Retry Configuration

Tasks can be automatically retried on failure:

```bash
# Enable retry with custom settings
bl task execute --max-retries 5 --poll-interval 30

# Disable retry
bl task execute --no-retry
```

### Timeout Handling

Set timeouts for task execution:

```bash
# Set 1-hour timeout
bl task execute --timeout 3600

# Set 30-minute timeout with retry
bl task execute --timeout 1800 --max-retries 2
```

## Best Practices

### Resource Management

1. **Use appropriate concurrency limits**:
   ```bash
   # For CPU-intensive tasks
   bl task execute --max-concurrent 2
   
   # For I/O-intensive tasks
   bl task execute --max-concurrent 5
   ```

2. **Set appropriate polling intervals**:
   ```bash
   # For fast tasks
   bl task execute --poll-interval 10
   
   # For long-running tasks
   bl task execute --poll-interval 60
   ```

### Monitoring

1. **Monitor task execution**:
   ```bash
   # Start monitoring before execution
   bl task monitor --interval 30 &
   bl task execute --limit 10
   ```

2. **Use verbose output for debugging**:
   ```bash
   bl task execute --verbose --output debug.json
   ```

### Slurm Integration

1. **Test Slurm connection**:
   ```bash
   bl resource slurm status --host login.cluster.edu --user myuser
   ```

2. **Use appropriate resource limits**:
   ```bash
   bl task execute --slurm --max-concurrent 3 --poll-interval 60
   ```

### Error Handling

1. **Enable retry for transient failures**:
   ```bash
   bl task execute --max-retries 3 --poll-interval 30
   ```

2. **Set appropriate timeouts**:
   ```bash
   bl task execute --timeout 3600 --max-retries 2
   ```

## Troubleshooting

### Debug Mode

Enable debug logging:

```bash
export PYBRAINLIFE_LOG_LEVEL=DEBUG
bl task execute --verbose
```

### Common Issues

#### Tasks Not Found
```bash
# Check available tasks
bl task list --status pending --limit 50

# Check project permissions
bl project list
```

#### Execution Failures
```bash
# Check resource status
bl resource list

# Test Slurm connection
bl resource slurm status --host login.cluster.edu --user myuser
```

#### Performance Issues
```bash
# Reduce concurrency
bl task execute --max-concurrent 1

# Increase polling interval
bl task execute --poll-interval 60
```

## Integration Examples

### Automated Workflows

#### Batch Processing
```bash
#!/bin/bash
# Process tasks in batches
for i in {1..5}; do
    echo "Processing batch $i"
    bl task execute --limit 10 --max-concurrent 2 --output "batch_$i.json"
    sleep 60
done
```

#### Continuous Monitoring
```bash
#!/bin/bash
# Continuous task monitoring and execution
while true; do
    bl task execute --limit 5 --max-concurrent 2
    bl task monitor --duration 300 --interval 30
    sleep 60
done
```

### Slurm Workflows

#### HPC Execution
```bash
#!/bin/bash
# Execute tasks on HPC cluster
bl task execute --slurm \
  --slurm-host login.cluster.edu \
  --slurm-user myuser \
  --slurm-key ~/.ssh/slurm_key \
  --max-concurrent 10 \
  --poll-interval 120 \
  --output hpc_results.json
```

## Support

For additional support with task execution:

1. Check the Brainlife documentation
2. Review the task execution examples
3. Contact your cluster administrator (for Slurm issues)
4. Submit issues to the pybrainlife repository

