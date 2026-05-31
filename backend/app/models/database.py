from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_all_tables() -> None:
    from app.models import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as connection:
            columns = connection.execute(text("PRAGMA table_info(workflow_runs)")).fetchall()
            column_names = {column[1] for column in columns}
            if "input_data" not in column_names:
                connection.execute(
                    text("ALTER TABLE workflow_runs ADD COLUMN input_data JSON NOT NULL DEFAULT '{}'")
                )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS workflow_run_steps (
                        id INTEGER NOT NULL PRIMARY KEY,
                        workflow_run_id INTEGER NOT NULL,
                        step_id VARCHAR(160) NOT NULL,
                        node_type VARCHAR(64) NOT NULL DEFAULT 'agent',
                        agent_id INTEGER,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        sequence INTEGER NOT NULL DEFAULT 0,
                        started_at DATETIME,
                        completed_at DATETIME,
                        agent_output TEXT,
                        context_snapshot JSON NOT NULL DEFAULT '{}',
                        error TEXT,
                        FOREIGN KEY(workflow_run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
                        FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE SET NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_workflow_run_steps_run_step "
                    "ON workflow_run_steps (workflow_run_id, step_id)"
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS agent_messages (
                        id INTEGER NOT NULL PRIMARY KEY,
                        sender_id INTEGER,
                        receiver_id INTEGER,
                        payload JSON NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        error TEXT,
                        delivered_at DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(sender_id) REFERENCES agents(id) ON DELETE SET NULL,
                        FOREIGN KEY(receiver_id) REFERENCES agents(id) ON DELETE SET NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS dlq (
                        id INTEGER NOT NULL PRIMARY KEY,
                        original_message_id INTEGER,
                        sender_id INTEGER,
                        receiver_id INTEGER,
                        payload JSON NOT NULL,
                        error_reason TEXT NOT NULL,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_agent_messages_status_id "
                    "ON agent_messages (status, id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_dlq_original_message "
                    "ON dlq (original_message_id)"
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_events (
                        id INTEGER NOT NULL PRIMARY KEY,
                        event_type VARCHAR(64) NOT NULL,
                        source VARCHAR(64) NOT NULL DEFAULT 'llm_router',
                        payload JSON NOT NULL DEFAULT '{}',
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_telemetry_events_type_created "
                    "ON telemetry_events (event_type, created_at)"
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id INTEGER NOT NULL PRIMARY KEY,
                        correlation_id VARCHAR(64),
                        event_type VARCHAR(64) NOT NULL,
                        agent_id INTEGER,
                        run_id INTEGER,
                        payload JSON NOT NULL DEFAULT '{}',
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_events_run_created "
                    "ON audit_events (run_id, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_events_correlation_created "
                    "ON audit_events (correlation_id, created_at)"
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                    BEFORE UPDATE ON audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_events is append-only');
                    END
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                    BEFORE DELETE ON audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_events is append-only');
                    END
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS memory_nodes (
                        id INTEGER NOT NULL PRIMARY KEY,
                        agent_id INTEGER NOT NULL,
                        node_type VARCHAR(32) NOT NULL,
                        source_id INTEGER,
                        content TEXT NOT NULL,
                        facts JSON NOT NULL DEFAULT '{}',
                        ttl_expires_at DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS memory_edges (
                        id INTEGER NOT NULL PRIMARY KEY,
                        source_node_id INTEGER NOT NULL,
                        target_node_id INTEGER NOT NULL,
                        edge_type VARCHAR(32) NOT NULL,
                        metadata JSON NOT NULL DEFAULT '{}',
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(source_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE,
                        FOREIGN KEY(target_node_id) REFERENCES memory_nodes(id) ON DELETE CASCADE
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_memory_nodes_agent_created "
                    "ON memory_nodes (agent_id, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_memory_edges_source_target "
                    "ON memory_edges (source_node_id, target_node_id)"
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS quota_counters (
                        id INTEGER NOT NULL PRIMARY KEY,
                        entity_id VARCHAR(160) NOT NULL,
                        quota_type VARCHAR(32) NOT NULL,
                        requests_count INTEGER NOT NULL DEFAULT 0,
                        tokens_used INTEGER NOT NULL DEFAULT 0,
                        concurrent_count INTEGER NOT NULL DEFAULT 0,
                        window_start DATETIME NOT NULL,
                        reset_at DATETIME NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_quota_counters_entity_type "
                    "ON quota_counters (entity_id, quota_type)"
                )
            )


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
