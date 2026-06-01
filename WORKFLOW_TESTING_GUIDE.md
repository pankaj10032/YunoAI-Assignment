# Workflow Testing Guide

## Overview
This guide will help you test the multi-agent workflow orchestration features of the AI Orchestrator system.

---

## Prerequisites

✅ Backend running on `http://localhost:8000`  
✅ Frontend running on `http://localhost:3000`  
✅ At least 2 agents created (for multi-agent workflows)  
✅ OpenAI API key configured in `.env`

---

## Table of Contents

1. [Understanding Workflows](#understanding-workflows)
2. [Creating Your First Workflow](#creating-your-first-workflow)
3. [Testing Single-Agent Workflows](#testing-single-agent-workflows)
4. [Testing Multi-Agent Workflows](#testing-multi-agent-workflows)
5. [Testing Workflow Templates](#testing-workflow-templates)
6. [Monitoring Workflow Execution](#monitoring-workflow-execution)
7. [Advanced Testing Scenarios](#advanced-testing-scenarios)
8. [Troubleshooting](#troubleshooting)

---

## Understanding Workflows

### What is a Workflow?

A workflow is a directed graph of agents that work together to complete complex tasks:
- **Nodes:** Represent agents or decision points
- **Edges:** Define the flow of data between agents
- **Input Data:** Initial context provided to the workflow
- **Output:** Final result after all agents complete their tasks

### Workflow Types

1. **Sequential:** Agents execute one after another (A → B → C)
2. **Parallel:** Multiple agents execute simultaneously
3. **Conditional:** Agents execute based on conditions
4. **Hybrid:** Combination of the above

---

## Creating Your First Workflow

### Step 1: Create Agents via UI

1. Open frontend: `http://localhost:3000`
2. Navigate to **Agents** page
3. Click **"Create Agent"**
4. Create two agents:

**Agent 1: Research Agent**
```
Name: Research Agent
Model: gpt-4o-mini
System Prompt: You are a research assistant. Analyze the given topic and provide key insights.
Channels: web
```

**Agent 2: Summary Agent**
```
Name: Summary Agent
Model: gpt-4o-mini
System Prompt: You are a summarization expert. Take research findings and create a concise summary.
Channels: web
```

### Step 2: Create Agents via API (Alternative)

```powershell
# Create Research Agent
$agent1 = @{
    name = "Research Agent"
    model = "gpt-4o-mini"
    system_prompt = "You are a research assistant. Analyze the given topic and provide key insights."
    channels = @("web")
    guardrails = @{}
} | ConvertTo-Json

$research = Invoke-RestMethod -Uri "http://localhost:8000/api/agents" -Method Post -Body $agent1 -ContentType "application/json" -UseBasicParsing
Write-Host "Research Agent ID: $($research.id)"

# Create Summary Agent
$agent2 = @{
    name = "Summary Agent"
    model = "gpt-4o-mini"
    system_prompt = "You are a summarization expert. Take research findings and create a concise summary."
    channels = @("web")
    guardrails = @{}
} | ConvertTo-Json

$summary = Invoke-RestMethod -Uri "http://localhost:8000/api/agents" -Method Post -Body $agent2 -ContentType "application/json" -UseBasicParsing
Write-Host "Summary Agent ID: $($summary.id)"
```

### Step 3: Create a Simple Workflow

```powershell
# Replace AGENT_ID_1 and AGENT_ID_2 with actual IDs from above
$workflow = @{
    name = "Research and Summarize"
    description = "Research a topic and create a summary"
    nodes = @(
        @{
            id = "research-node"
            type = "agent"
            data = @{
                agent_id = 1  # Replace with actual Research Agent ID
                label = "Research Agent"
            }
            position = @{ x = 100; y = 100 }
        },
        @{
            id = "summary-node"
            type = "agent"
            data = @{
                agent_id = 2  # Replace with actual Summary Agent ID
                label = "Summary Agent"
            }
            position = @{ x = 300; y = 100 }
        }
    )
    edges = @(
        @{
            id = "edge-1"
            source = "research-node"
            target = "summary-node"
            type = "default"
        }
    )
    is_template = $false
} | ConvertTo-Json -Depth 10

$wf = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows" -Method Post -Body $workflow -ContentType "application/json" -UseBasicParsing
Write-Host "Workflow ID: $($wf.id)"
```

---

## Testing Single-Agent Workflows

### Test 1: Direct Agent Execution

```powershell
# Execute a single agent directly
$execution = @{
    task_description = "Explain quantum computing in simple terms"
} | ConvertTo-Json

$run = Invoke-RestMethod -Uri "http://localhost:8000/api/agents/1/execute" -Method Post -Body $execution -ContentType "application/json" -UseBasicParsing

Write-Host "Run ID: $($run.run_id)"
Write-Host "Status: $($run.status)"
Write-Host "WebSocket URL: $($run.websocket_url)"
```

### Test 2: Monitor Execution

```powershell
# Check run status
$runId = 1  # Replace with actual run ID
$status = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/$runId" -UseBasicParsing
Write-Host "Status: $($status.status)"
Write-Host "Started: $($status.started_at)"
Write-Host "Completed: $($status.completed_at)"

# Get messages
$messages = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/$runId/messages" -UseBasicParsing
$messages | ForEach-Object {
    Write-Host "[$($_.timestamp)] $($_.content)"
}
```

---

## Testing Multi-Agent Workflows

### Test 3: Sequential Workflow Execution

```powershell
# Run the workflow created earlier
$workflowId = 1  # Replace with actual workflow ID
$input = @{
    input_data = @{
        topic = "Artificial Intelligence in Healthcare"
        depth = "detailed"
    }
} | ConvertTo-Json

$run = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows/$workflowId/run" -Method Post -Body $input -ContentType "application/json" -UseBasicParsing

Write-Host "Workflow Run ID: $($run.run_id)"
Write-Host "Status: $($run.status)"
```

### Test 4: Parallel Agent Workflow

Create a workflow with parallel execution:

```powershell
$parallelWorkflow = @{
    name = "Parallel Analysis"
    description = "Multiple agents analyze different aspects simultaneously"
    nodes = @(
        @{
            id = "agent-1"
            type = "agent"
            data = @{ agent_id = 1; label = "Technical Analysis" }
            position = @{ x = 100; y = 100 }
        },
        @{
            id = "agent-2"
            type = "agent"
            data = @{ agent_id = 2; label = "Business Analysis" }
            position = @{ x = 100; y = 200 }
        },
        @{
            id = "agent-3"
            type = "agent"
            data = @{ agent_id = 3; label = "Summary" }
            position = @{ x = 300; y = 150 }
        }
    )
    edges = @(
        @{
            id = "edge-1"
            source = "agent-1"
            target = "agent-3"
        },
        @{
            id = "edge-2"
            source = "agent-2"
            target = "agent-3"
        }
    )
    is_template = $false
} | ConvertTo-Json -Depth 10

$parallel = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows" -Method Post -Body $parallelWorkflow -ContentType "application/json" -UseBasicParsing
```

---

## Testing Workflow Templates

### Test 5: List Available Templates

```powershell
# Get workflow templates
$templates = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows?templates_only=true" -UseBasicParsing
$templates | ForEach-Object {
    Write-Host "Template: $($_.name)"
    Write-Host "  Description: $($_.description)"
    Write-Host "  Nodes: $($_.nodes.Count)"
    Write-Host ""
}
```

### Test 6: Use a Template

```powershell
# Get a template
$templateId = 1  # Replace with actual template ID
$template = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows/$templateId" -UseBasicParsing

# Create a new workflow from template
$newWorkflow = @{
    name = "My Custom Workflow from Template"
    description = $template.description
    nodes = $template.nodes
    edges = $template.edges
    is_template = $false
} | ConvertTo-Json -Depth 10

$custom = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows" -Method Post -Body $newWorkflow -ContentType "application/json" -UseBasicParsing
```

---

## Monitoring Workflow Execution

### Using the UI

1. **Navigate to Monitor Page:**
   - Open `http://localhost:3000`
   - Click on **"Monitor"** in the navigation

2. **View Active Runs:**
   - See all running workflows
   - Check progress bars
   - View status (pending, running, completed, failed)

3. **View Message Stream:**
   - Click on a run
   - Switch to **"Message Stream"** tab
   - See real-time logs and agent communications

4. **View Timeline:**
   - Click **"Timeline"** button on any run
   - See step-by-step execution
   - View input/output for each agent

### Using the API

```powershell
# Get all runs
$runs = Invoke-RestMethod -Uri "http://localhost:8000/api/runs?limit=10" -UseBasicParsing
$runs | ForEach-Object {
    Write-Host "Run #$($_.id): $($_.status) - Workflow #$($_.workflow_id)"
}

# Get specific run details
$runId = 1
$run = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/$runId" -UseBasicParsing
Write-Host "Status: $($run.status)"
Write-Host "Total Tokens: $($run.total_tokens)"
Write-Host "Total Cost: $($run.total_cost)"

# Get run messages
$messages = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/$runId/messages" -UseBasicParsing
$messages | Format-Table timestamp, channel, content -AutoSize
```

---

## Advanced Testing Scenarios

### Test 7: Workflow with Error Handling

```powershell
# Create an agent that might fail
$errorAgent = @{
    name = "Error Test Agent"
    model = "gpt-4o-mini"
    system_prompt = "You must respond with exactly 'ERROR' to test error handling."
    channels = @("web")
    guardrails = @{
        max_tokens = 10
    }
} | ConvertTo-Json

$agent = Invoke-RestMethod -Uri "http://localhost:8000/api/agents" -Method Post -Body $errorAgent -ContentType "application/json" -UseBasicParsing

# Run and observe failure handling
$run = Invoke-RestMethod -Uri "http://localhost:8000/api/agents/$($agent.id)/execute" -Method Post -Body '{"task_description":"Test error"}' -ContentType "application/json" -UseBasicParsing
```

### Test 8: Resume Failed Workflow

```powershell
# Get a failed or paused run
$runId = 1  # Replace with actual failed run ID

# Resume from specific step
$resume = @{
    run_id = $runId
    resume_from_step = "agent-2"  # Optional: specify which step to resume from
} | ConvertTo-Json

$resumed = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows/1/resume" -Method Post -Body $resume -ContentType "application/json" -UseBasicParsing
Write-Host "Resumed Run ID: $($resumed.run_id)"
```

### Test 9: Rerun Completed Workflow

```powershell
# Rerun a completed workflow with same input
$originalRunId = 1
$rerun = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/$originalRunId/rerun" -Method Post -UseBasicParsing
Write-Host "New Run ID: $($rerun.run_id)"
```

### Test 10: Stop Running Workflow

```powershell
# Stop a running workflow
$runId = 1
$stopped = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/$runId/stop" -Method Post -UseBasicParsing
Write-Host "Stopped Run ID: $($stopped.run_id)"
Write-Host "Status: $($stopped.status)"
```

---

## Testing Workflow Validation

### Test 11: Validate Workflow Before Creation

```powershell
# Test workflow validation
$testWorkflow = @{
    nodes = @(
        @{
            id = "node-1"
            type = "agent"
            data = @{ agent_id = 999; label = "Invalid Agent" }  # Non-existent agent
            position = @{ x = 0; y = 0 }
        }
    )
    edges = @()
} | ConvertTo-Json -Depth 10

$validation = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows/validate" -Method Post -Body $testWorkflow -ContentType "application/json" -UseBasicParsing
Write-Host "Valid: $($validation.valid)"
if (-not $validation.valid) {
    Write-Host "Errors:"
    $validation.errors | ForEach-Object { Write-Host "  - $_" }
}
```

---

## Complete Testing Script

Save this as `test_workflows.ps1`:

```powershell
# Complete Workflow Testing Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Orchestrator Workflow Testing" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$baseUrl = "http://localhost:8000"

# 1. Check system health
Write-Host "1. Checking system health..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$baseUrl/health" -UseBasicParsing
    Write-Host "   ✓ System Status: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "   ✗ System not responding" -ForegroundColor Red
    exit
}

# 2. List existing agents
Write-Host "`n2. Listing agents..." -ForegroundColor Yellow
$agents = Invoke-RestMethod -Uri "$baseUrl/api/agents" -UseBasicParsing
Write-Host "   ✓ Found $($agents.Count) agent(s)" -ForegroundColor Green
$agents | ForEach-Object {
    Write-Host "      - ID: $($_.id), Name: $($_.name), Model: $($_.model)" -ForegroundColor Cyan
}

if ($agents.Count -lt 2) {
    Write-Host "   ⚠ Need at least 2 agents for workflow testing" -ForegroundColor Yellow
    Write-Host "   Creating test agents..." -ForegroundColor Yellow
    
    # Create agents if needed
    # ... (agent creation code here)
}

# 3. List existing workflows
Write-Host "`n3. Listing workflows..." -ForegroundColor Yellow
$workflows = Invoke-RestMethod -Uri "$baseUrl/api/workflows" -UseBasicParsing
Write-Host "   ✓ Found $($workflows.Count) workflow(s)" -ForegroundColor Green
$workflows | ForEach-Object {
    Write-Host "      - ID: $($_.id), Name: $($_.name)" -ForegroundColor Cyan
}

# 4. Create a test workflow
Write-Host "`n4. Creating test workflow..." -ForegroundColor Yellow
if ($agents.Count -ge 2) {
    $workflow = @{
        name = "Test Workflow $(Get-Date -Format 'HHmmss')"
        description = "Automated test workflow"
        nodes = @(
            @{
                id = "node-1"
                type = "agent"
                data = @{
                    agent_id = $agents[0].id
                    label = $agents[0].name
                }
                position = @{ x = 100; y = 100 }
            },
            @{
                id = "node-2"
                type = "agent"
                data = @{
                    agent_id = $agents[1].id
                    label = $agents[1].name
                }
                position = @{ x = 300; y = 100 }
            }
        )
        edges = @(
            @{
                id = "edge-1"
                source = "node-1"
                target = "node-2"
                type = "default"
            }
        )
        is_template = $false
    } | ConvertTo-Json -Depth 10
    
    $newWorkflow = Invoke-RestMethod -Uri "$baseUrl/api/workflows" -Method Post -Body $workflow -ContentType "application/json" -UseBasicParsing
    Write-Host "   ✓ Created workflow ID: $($newWorkflow.id)" -ForegroundColor Green
    
    # 5. Run the workflow
    Write-Host "`n5. Running workflow..." -ForegroundColor Yellow
    $input = @{
        input_data = @{
            task = "Test workflow execution"
            timestamp = (Get-Date).ToString()
        }
    } | ConvertTo-Json
    
    $run = Invoke-RestMethod -Uri "$baseUrl/api/workflows/$($newWorkflow.id)/run" -Method Post -Body $input -ContentType "application/json" -UseBasicParsing
    Write-Host "   ✓ Started run ID: $($run.run_id)" -ForegroundColor Green
    Write-Host "   ✓ Status: $($run.status)" -ForegroundColor Green
    Write-Host "   ✓ WebSocket: $($run.websocket_url)" -ForegroundColor Cyan
    
    # 6. Monitor execution
    Write-Host "`n6. Monitoring execution..." -ForegroundColor Yellow
    Write-Host "   Waiting for completion (max 30 seconds)..." -ForegroundColor Cyan
    
    $maxWait = 30
    $waited = 0
    $finalStatus = $null
    
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 2
        $waited += 2
        
        $status = Invoke-RestMethod -Uri "$baseUrl/api/runs/$($run.run_id)" -UseBasicParsing
        Write-Host "   Status: $($status.status) (${waited}s)" -ForegroundColor Cyan
        
        if ($status.status -in @("completed", "failed", "paused")) {
            $finalStatus = $status
            break
        }
    }
    
    if ($finalStatus) {
        Write-Host "   ✓ Final Status: $($finalStatus.status)" -ForegroundColor Green
        Write-Host "   ✓ Tokens Used: $($finalStatus.total_tokens)" -ForegroundColor Green
        Write-Host "   ✓ Cost: `$$($finalStatus.total_cost)" -ForegroundColor Green
        
        # Get messages
        $messages = Invoke-RestMethod -Uri "$baseUrl/api/runs/$($run.run_id)/messages" -UseBasicParsing
        Write-Host "   ✓ Messages: $($messages.Count)" -ForegroundColor Green
    } else {
        Write-Host "   ⚠ Workflow still running after ${maxWait}s" -ForegroundColor Yellow
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Testing Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Open UI: http://localhost:3000" -ForegroundColor White
Write-Host "2. Go to Monitor page to see execution details" -ForegroundColor White
Write-Host "3. Check Message Stream for logs" -ForegroundColor White
Write-Host "4. View Timeline for step-by-step execution" -ForegroundColor White
Write-Host ""
```

Run with: `powershell -File test_workflows.ps1`

---

## Troubleshooting

### Workflow Not Starting

**Check:**
```powershell
# Verify agents exist
$agents = Invoke-RestMethod -Uri "http://localhost:8000/api/agents" -UseBasicParsing
$agents | Format-Table id, name, model

# Verify workflow structure
$workflow = Invoke-RestMethod -Uri "http://localhost:8000/api/workflows/1" -UseBasicParsing
$workflow.nodes | Format-Table id, type, data
```

### Workflow Stuck in "Running"

**Check:**
```powershell
# View run details
$run = Invoke-RestMethod -Uri "http://localhost:8000/api/runs/1" -UseBasicParsing
Write-Host "Status: $($run.status)"
Write-Host "Started: $($run.started_at)"

# Check backend logs
docker-compose logs backend --tail=50
```

### Agent Not Responding

**Check:**
```powershell
# Verify OpenAI API key
docker-compose logs backend | Select-String -Pattern "OPENAI"

# Test agent directly
$test = @{ task_description = "Hello" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/api/agents/1/execute" -Method Post -Body $test -ContentType "application/json" -UseBasicParsing
```

### WebSocket Connection Issues

**Check:**
```powershell
# Check if WebSocket endpoint is accessible
# Open browser console at http://localhost:3000
# Look for WebSocket connection errors

# Check backend logs for WebSocket errors
docker-compose logs backend | Select-String -Pattern "websocket|WebSocket"
```

---

## Best Practices

1. **Start Simple:** Test single agents before complex workflows
2. **Use Templates:** Leverage workflow templates for common patterns
3. **Monitor Costs:** Check token usage and costs regularly
4. **Handle Errors:** Always test error scenarios
5. **Version Control:** Save successful workflow configurations
6. **Document:** Keep notes on what works for your use cases

---

## Additional Resources

- **API Documentation:** http://localhost:8000/docs
- **Frontend UI:** http://localhost:3000
- **Architecture Guide:** See `ARCHITECTURE.md`
- **Telegram Testing:** See `TELEGRAM_TESTING_GUIDE.md`

---

## Quick Reference

### Common API Endpoints

```
GET    /api/workflows              # List workflows
POST   /api/workflows              # Create workflow
GET    /api/workflows/{id}         # Get workflow
PUT    /api/workflows/{id}         # Update workflow
DELETE /api/workflows/{id}         # Delete workflow
POST   /api/workflows/{id}/run     # Run workflow
POST   /api/workflows/{id}/resume  # Resume workflow
POST   /api/runs/{id}/rerun        # Rerun workflow
POST   /api/runs/{id}/stop         # Stop workflow
GET    /api/runs                   # List runs
GET    /api/runs/{id}              # Get run details
GET    /api/runs/{id}/messages     # Get run messages
```

### Workflow Status Values

- `pending` - Workflow queued, not started
- `running` - Workflow currently executing
- `completed` - Workflow finished successfully
- `failed` - Workflow encountered an error
- `paused` - Workflow stopped by user

---

Happy Testing! 🚀
