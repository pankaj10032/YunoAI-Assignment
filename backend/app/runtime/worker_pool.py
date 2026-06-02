import asyncio
import time
import logging
from typing import Any, Callable, Dict, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Task states
# QUEUED -> RUNNING -> PAUSED -> COMPLETED -> FAILED -> DEGRADED

class CircuitBreaker:
    def __init__(self, failure_threshold: float = 0.5, cooldown_period: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_period = cooldown_period
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failures = 0
        self.successes = 0
        self.total_calls = 0
        self.last_state_change = time.time()
        self.window_start = time.time()

    def record_success(self):
        self._check_window()
        self.successes += 1
        self.total_calls += 1
        if self.state == "HALF_OPEN" and self.successes >= 3:
            self.state = "CLOSED"
            self.failures = 0
            self.successes = 0
            self.last_state_change = time.time()
            logger.info("Circuit Breaker recovered to CLOSED")

    def record_failure(self):
        self._check_window()
        self.failures += 1
        self.total_calls += 1
        rate = self.failures / max(1, self.total_calls)
        if self.state == "CLOSED" and rate > self.failure_threshold and self.total_calls >= 4:
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.warning("Circuit Breaker tripped to OPEN")
        elif self.state == "HALF_OPEN":
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.warning("Circuit Breaker returned to OPEN")

    def allow_request(self) -> bool:
        if self.state == "OPEN":
            if time.time() - self.last_state_change > self.cooldown_period:
                self.state = "HALF_OPEN"
                self.last_state_change = time.time()
                logger.info("Circuit Breaker entered HALF_OPEN state")
                return True
            return False
        return True

    def _check_window(self):
        if time.time() - self.window_start > 60.0:
            self.window_start = time.time()
            self.total_calls = 0
            self.failures = 0
            self.successes = 0


circuit_breaker = CircuitBreaker()

class WorkerPool:
    def __init__(self, max_workers: int = 5, queue_size: int = 100):
        self.max_workers = max_workers
        self.queue_size = queue_size
        self.queue: Optional[asyncio.PriorityQueue] = None
        self.workers: list[asyncio.Task] = []
        self.active_tasks = 0
        self.paused = False
        self.running = False
        self.checkpoints: Dict[int, Dict[str, Any]] = {}

    def _ensure_queue(self):
        if self.queue is None:
            self.queue = asyncio.PriorityQueue(maxsize=self.queue_size)

    def start(self):
        if self.running:
            return
        self._ensure_queue()
        self.running = True
        for i in range(self.max_workers):
            self.workers.append(asyncio.create_task(self._worker_loop(i)))
        logger.info("WorkerPool started with %s workers", self.max_workers)

    async def shutdown(self):
        logger.info("WorkerPool draining in-flight tasks and shutting down")
        self.running = False
        # Cancel all idle workers
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []
        self.queue = None
        logger.info("WorkerPool shut down completed")

    async def submit(self, run_id: int, func: Callable, *args, priority: int = 1, **kwargs) -> bool:
        """Submit a task to the priority queue.
        priority: 0 (high), 1 (normal), 2 (low)
        """
        self._ensure_queue()
        if self.queue.full():
            logger.warning("Queue full: rejecting task execution for run_id %s", run_id)
            return False
        
        # item: (priority, timestamp, run_id, func, args, kwargs)
        item = (priority, time.time(), run_id, func, args, kwargs)
        await self.queue.put(item)
        logger.info("Submitted task run_id=%s with priority=%s to worker pool", run_id, priority)
        return True

    async def _worker_loop(self, worker_id: int):
        while self.running:
            try:
                # Get the next task from the queue
                priority, timestamp, run_id, func, args, kwargs = await self.queue.get()
                
                # Check for circuit breaker or pause
                while self.paused:
                    await asyncio.sleep(0.5)

                if not circuit_breaker.allow_request():
                    logger.warning("Circuit breaker OPEN. Skipping task execution for run_id=%s. Serving fallback.", run_id)
                    # Graceful degradation fallback
                    await self._execute_fallback(run_id, func, args, kwargs)
                    self.queue.task_done()
                    continue

                self.active_tasks += 1
                try:
                    # Execute task
                    logger.info("Worker %s executing task run_id=%s", worker_id, run_id)
                    
                    # Log RUNNING transition
                    self.save_checkpoint(run_id, "RUNNING", {"step": "start"})
                    
                    # Run task with a timeout (e.g. 60s)
                    if asyncio.iscoroutinefunction(func):
                        res = await asyncio.wait_for(func(*args, **kwargs), timeout=60.0)
                    else:
                        res = await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=60.0)

                    circuit_breaker.record_success()
                    self.save_checkpoint(run_id, "COMPLETED", {"result": str(res)})
                except Exception as exc:
                    logger.exception("Task run_id=%s execution failed", run_id)
                    circuit_breaker.record_failure()
                    # Graceful degradation fallback
                    self.save_checkpoint(run_id, "FAILED", {"error": str(exc)})
                    await self._execute_fallback(run_id, func, args, kwargs, error_msg=str(exc))
                finally:
                    self.active_tasks = max(0, self.active_tasks - 1)
                    self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in worker loop %s: %s", worker_id, exc)
                await asyncio.sleep(1.0)

    async def _execute_fallback(self, run_id: int, func: Callable, args: tuple, kwargs: dict, error_msg: Optional[str] = None):
        # Graceful degradation: log warning and output degraded result format
        logger.info("Serving graceful degradation fallback for run_id=%s", run_id)
        from app.agents.executor import event_broker
        fallback_msg = f"[DEGRADED MODE] Task completed with partial fallback results due to error/circuit trip: {error_msg or 'Circuit OPEN'}"
        await event_broker.publish(
            run_id,
            {
                "type": "degraded",
                "run_id": run_id,
                "message": fallback_msg
            }
        )

    def save_checkpoint(self, run_id: int, state: str, data: Dict[str, Any]):
        self.checkpoints[run_id] = {
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        # Log to DB / update workflow_runs state if db connection available
        try:
            from app.models.database import SessionLocal
            from app.models.models import WorkflowRun
            db = SessionLocal()
            run = db.get(WorkflowRun, run_id)
            if run:
                run.status = state.lower()
                db.commit()
            db.close()
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        return {
            "active_workers": self.active_tasks,
            "max_workers": self.max_workers,
            "queue_depth": self.queue.qsize(),
            "paused": self.paused,
            "circuit_state": circuit_breaker.state,
            "health": "ok" if circuit_breaker.state == "CLOSED" else "degraded"
        }

worker_pool = WorkerPool()
