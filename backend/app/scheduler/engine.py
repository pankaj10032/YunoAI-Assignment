import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.agents.executor import create_workflow_run, execute_agent_background
from app.config import settings
from app.models.database import SessionLocal
from app.models.models import Agent, SchedulerMissedRun, Workflow

logger = logging.getLogger(__name__)


_engine_instance: "SchedulerEngine | None" = None


async def _scheduled_run_job_wrapper(agent_id: int) -> None:
    if _engine_instance is not None:
        await _engine_instance._handle_scheduled_run(agent_id)


class SchedulerEngine:
    def __init__(self):
        global _engine_instance
        _engine_instance = self
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=settings.scheduler_job_store_url)}
        )
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self.global_semaphore = asyncio.Semaphore(settings.scheduler_max_concurrent_jobs)
        self.agent_locks: dict[int, asyncio.Lock] = {}
        self._signal_installed = False

    async def start(self) -> None:
        self._install_signal_handlers()
        self.scheduler.start()
        await self._load_schedules()
        # await self._run_backfill()
        logger.info("Scheduler started with job store %s", settings.scheduler_job_store_url)

    async def shutdown(self) -> None:
        logger.info("Shutting down scheduler")
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except Exception as exc:
            logger.exception("Scheduler shutdown failed: %s", exc)

    def _install_signal_handlers(self) -> None:
        if self._signal_installed:
            return
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            self._signal_installed = True
        except (ValueError, AttributeError) as exc:
            logger.debug("Unable to install SIGTERM handler for scheduler: %s", exc)

    def _signal_handler(self, signum, frame):
        logger.info("Received signal %s, shutting down scheduler", signum)
        loop = asyncio.get_event_loop()
        loop.create_task(self.shutdown())

    def _job_id(self, agent_id: int) -> str:
        return f"scheduled_agent_{agent_id}"

    def _build_trigger(self, schedule: dict[str, Any]) -> CronTrigger:
        cron_expression = schedule.get("cron")
        timezone_name = schedule.get("timezone") or "UTC"
        if not cron_expression:
            raise ValueError("Schedule must include a cron expression")
        return CronTrigger.from_crontab(cron_expression, timezone=ZoneInfo(timezone_name))

    async def _load_schedules(self) -> None:
        with SessionLocal() as db:
            agents = db.query(Agent).filter(Agent.schedule.is_not(None)).all()
            for agent in agents:
                self._register_agent_schedule(agent, db)

    def _register_agent_schedule(self, agent: Agent, db: Session) -> None:
        schedule = agent.schedule or {}
        if not self._is_schedule_active(schedule):
            self._remove_job(agent.id)
            return

        try:
            trigger = self._build_trigger(schedule)
        except Exception as exc:
            logger.warning("Invalid schedule for agent %s: %s", agent.id, exc)
            self._remove_job(agent.id)
            return

        job_id = self._job_id(agent.id)
        self.scheduler.add_job(
            _scheduled_run_job_wrapper,
            trigger=trigger,
            args=[agent.id],
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=False,
            misfire_grace_time=60,
        )

        job = self.scheduler.get_job(job_id)
        if job and job.next_run_time:
            agent.next_run_at = job.next_run_time
            db.commit()

    def _remove_job(self, agent_id: int) -> None:
        job_id = self._job_id(agent_id)
        if self.scheduler.get_job(job_id) is not None:
            self.scheduler.remove_job(job_id)

    async def _run_backfill(self) -> None:
        with SessionLocal() as db:
            missed_runs = (
                db.query(SchedulerMissedRun)
                .filter(SchedulerMissedRun.status == "pending")
                .order_by(SchedulerMissedRun.scheduled_at.asc())
                .limit(5)
                .all()
            )
            for missed_run in missed_runs:
                db.expunge(missed_run)

        for missed_run in missed_runs:
            asyncio.create_task(self._process_missed_run(missed_run))

        with SessionLocal() as db:
            scheduled_agents = db.query(Agent).filter(Agent.schedule.is_not(None)).all()
            now = datetime.now(timezone.utc)
            for agent in scheduled_agents:
                schedule = agent.schedule or {}
                if not self._is_schedule_active(schedule) or not agent.last_run_at:
                    continue
                missed_times = self._collect_missed_fire_times(schedule, agent.last_run_at, now)
                for missed_time in missed_times[:5]:
                    self._enqueue_missed_run(db, agent.id, missed_time, "restart_backfill")
                if missed_times:
                    db.commit()
            pending = (
                db.query(SchedulerMissedRun)
                .filter(SchedulerMissedRun.status == "pending")
                .order_by(SchedulerMissedRun.scheduled_at.asc())
                .limit(5)
                .all()
            )
            for missed_run in pending:
                db.expunge(missed_run)

        for missed_run in pending:
            asyncio.create_task(self._process_missed_run(missed_run))

    def _collect_missed_fire_times(
        self,
        schedule: dict[str, Any],
        last_run_at: datetime,
        reference_time: datetime,
    ) -> list[datetime]:
        if not last_run_at:
            return []
        trigger = self._build_trigger(schedule)
        missed_times: list[datetime] = []
        next_fire = trigger.get_next_fire_time(last_run_at, reference_time)
        while next_fire and next_fire <= reference_time and len(missed_times) < 5:
            missed_times.append(next_fire)
            next_fire = trigger.get_next_fire_time(next_fire, reference_time)
        return missed_times

    def _enqueue_missed_run(
        self,
        db: Session,
        agent_id: int,
        scheduled_at: datetime,
        reason: str,
    ) -> None:
        missed_run = SchedulerMissedRun(
            agent_id=agent_id,
            scheduled_at=scheduled_at,
            status="pending",
            reason=reason,
        )
        db.add(missed_run)

    async def _process_missed_run(self, missed_run: SchedulerMissedRun) -> None:
        if missed_run.status != "pending":
            return
            
        lock = self._get_agent_lock(missed_run.agent_id)
        if lock.locked():
            return
            
        async with lock:
            with SessionLocal() as db:
                agent = db.get(Agent, missed_run.agent_id)
                if not agent or not self._is_schedule_active(agent.schedule or {}):
                    missed_run.status = "skipped"
                    missed_run.processed_at = datetime.now(timezone.utc)
                    db.merge(missed_run)
                    db.commit()
                    return
            
            await self._execute_scheduled_agent(missed_run.agent_id, missed_run.scheduled_at)
            
            with SessionLocal() as db:
                missed_run.status = "processed"
                missed_run.processed_at = datetime.now(timezone.utc)
                db.merge(missed_run)
                db.commit()

    async def _handle_scheduled_run(self, agent_id: int) -> None:
        async with self.global_semaphore:
            lock = self._get_agent_lock(agent_id)
            if lock.locked():
                await self._record_missed_run(agent_id, datetime.now(timezone.utc), "overlap")
                return
            async with lock:
                with SessionLocal() as db:
                    agent = db.get(Agent, agent_id)
                    if not agent or not self._is_schedule_active(agent.schedule or {}):
                        return
                
                await self._execute_scheduled_agent(agent_id)

    async def _execute_scheduled_agent(
        self,
        agent_id: int,
        scheduled_at: datetime | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            agent = db.get(Agent, agent_id)
            if not agent:
                return

            workflow = Workflow(
                name=f"Scheduled run: {agent.name}",
                description="Scheduled execution for agent.",
                nodes=[
                    {
                        "id": f"agent-{agent.id}",
                        "type": "agent",
                        "data": {"agent_id": agent.id, "label": agent.name},
                        "position": {"x": 0, "y": 0},
                    }
                ],
                edges=[],
                is_template=False,
            )
            db.add(workflow)
            db.commit()
            db.refresh(workflow)

            run = create_workflow_run(db, workflow.id, {"scheduled_run": True})
            agent.last_run_at = scheduled_at or now
            agent.run_count = (agent.run_count or 0) + 1
            agent.next_run_at = self._compute_next_fire_time(agent.schedule or {}, agent.last_run_at)
            db.commit()

        await asyncio.to_thread(
            execute_agent_background,
            run.id,
            agent_id,
            "Scheduled run",
            None,
        )

    def _is_schedule_active(self, schedule: dict[str, Any]) -> bool:
        return bool(schedule.get("enabled", False)) and not bool(schedule.get("paused", False)) and bool(
            schedule.get("cron")
        )

    def _get_agent_lock(self, agent_id: int) -> asyncio.Lock:
        if agent_id not in self.agent_locks:
            self.agent_locks[agent_id] = asyncio.Lock()
        return self.agent_locks[agent_id]

    async def _record_missed_run(self, agent_id: int, scheduled_at: datetime, reason: str) -> None:
        with SessionLocal() as db:
            self._enqueue_missed_run(db, agent_id, scheduled_at, reason)
            db.commit()

    def _compute_next_fire_time(
        self, schedule: dict[str, Any], last_run_at: datetime | None
    ) -> datetime | None:
        if not last_run_at or not schedule.get("cron"):
            return None
        trigger = self._build_trigger(schedule)
        return trigger.get_next_fire_time(last_run_at, datetime.now(timezone.utc))

    def _job_listener(self, event):
        if event.exception:
            logger.error("Scheduled job failed: %s", event.exception)
        else:
            logger.info("Scheduled job completed: %s", event.job_id)

    def get_schedule_status(self) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            agents = db.query(Agent).filter(Agent.schedule.is_not(None)).all()
            items: list[dict[str, any]] = []
            for agent in agents:
                schedule = agent.schedule or {}
                missed_run_count = (
                    db.query(SchedulerMissedRun)
                    .filter(
                        SchedulerMissedRun.agent_id == agent.id,
                        SchedulerMissedRun.status == "pending",
                    )
                    .count()
                )
                items.append(
                    {
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "enabled": bool(schedule.get("enabled", False)),
                        "paused": bool(schedule.get("paused", False)),
                        "cron": schedule.get("cron"),
                        "timezone": schedule.get("timezone", "UTC"),
                        "last_run_at": agent.last_run_at,
                        "next_run_at": agent.next_run_at,
                        "run_count": agent.run_count or 0,
                        "missed_runs": missed_run_count,
                    }
                )
            return items

    def pause_agent_schedule(self, agent_id: int) -> dict[str, any]:
        with SessionLocal() as db:
            agent = db.get(Agent, agent_id)
            if not agent or not agent.schedule:
                raise ValueError("Agent schedule not found")
            schedule = dict(agent.schedule or {})
            schedule["enabled"] = False
            schedule["paused"] = True
            agent.schedule = schedule
            db.commit()
            db.refresh(agent)
            self._remove_job(agent_id)
            return {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "enabled": False,
                "paused": True,
                "cron": schedule.get("cron"),
                "timezone": schedule.get("timezone", "UTC"),
                "last_run_at": agent.last_run_at,
                "next_run_at": agent.next_run_at,
                "run_count": agent.run_count or 0,
                "missed_runs": 0,
            }

    def resume_agent_schedule(self, agent_id: int) -> dict[str, any]:
        with SessionLocal() as db:
            agent = db.get(Agent, agent_id)
            if not agent or not agent.schedule:
                raise ValueError("Agent schedule not found")
            schedule = dict(agent.schedule or {})
            schedule["enabled"] = True
            schedule["paused"] = False
            agent.schedule = schedule
            db.commit()
            db.refresh(agent)
            self._register_agent_schedule(agent, db)
            missed_run_count = (
                db.query(SchedulerMissedRun)
                .filter(
                    SchedulerMissedRun.agent_id == agent.id,
                    SchedulerMissedRun.status == "pending",
                )
                .count()
            )
            return {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "enabled": True,
                "paused": False,
                "cron": schedule.get("cron"),
                "timezone": schedule.get("timezone", "UTC"),
                "last_run_at": agent.last_run_at,
                "next_run_at": agent.next_run_at,
                "run_count": agent.run_count or 0,
                "missed_runs": missed_run_count,
            }
