import asyncio
import pytest
from app.models.models import Workflow, WorkflowRun
from app.runtime.worker_pool import worker_pool, circuit_breaker

@pytest.mark.asyncio
async def test_worker_pool_concurrency_and_priority(db):
    # Register basic tasks in worker pool
    executed = []

    async def sample_task(val: int):
        await asyncio.sleep(0.1)
        executed.append(val)
        return val

    # Submit 3 tasks with different priorities
    await worker_pool.submit(1001, sample_task, 3, priority=2) # Low
    await worker_pool.submit(1002, sample_task, 1, priority=0) # High
    await worker_pool.submit(1003, sample_task, 2, priority=1) # Normal

    await asyncio.sleep(1.0)
    assert len(executed) >= 3
    # High priority task should execute first
    assert executed[0] == 1


@pytest.mark.asyncio
async def test_circuit_breaker_tripping_and_fallback():
    # Reset circuit breaker
    circuit_breaker.state = "CLOSED"
    circuit_breaker.failures = 0
    circuit_breaker.total_calls = 0

    # Simulate 5 consecutive failures
    for _ in range(5):
        circuit_breaker.record_failure()

    # The circuit should trip to OPEN
    assert circuit_breaker.state == "OPEN"
    assert circuit_breaker.allow_request() is False


@pytest.mark.asyncio
async def test_checkpoint_saving_and_resume(db):
    run_id = 999
    worker_pool.save_checkpoint(run_id, "RUNNING", {"current_step": "step_1"})
    
    checkpoint = worker_pool.checkpoints.get(run_id)
    assert checkpoint is not None
    assert checkpoint["state"] == "RUNNING"
    assert checkpoint["data"]["current_step"] == "step_1"
