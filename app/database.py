import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import contextlib

class DatabaseManager:
    def __init__(self, db_path: str = "workflows.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            # Workflows table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step INTEGER DEFAULT 0,
                    priority INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    steps TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    execution_log TEXT NOT NULL,
                    rollback_data TEXT
                )
            ''')

            # Approval requests table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    requested_by TEXT NOT NULL,
                    approval_level INTEGER DEFAULT 1,
                    metadata TEXT NOT NULL,
                    timeout_at TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
                )
            ''')

            # Approval responses table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS approval_responses (
                    id TEXT PRIMARY KEY,
                    approval_request_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    comments TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (approval_request_id) REFERENCES approval_requests (id)
                )
            ''')

            # System metrics table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active_workflows INTEGER DEFAULT 0,
                    pending_approvals INTEGER DEFAULT 0,
                    completed_today INTEGER DEFAULT 0,
                    avg_completion_time REAL DEFAULT 0
                )
            ''')

            conn.commit()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def save_workflow(self, workflow: Dict[str, Any]) -> str:
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO workflows 
                (id, name, description, task_type, status, current_step, priority, 
                 created_at, steps, metadata, execution_log, rollback_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                workflow['id'],
                workflow['name'],
                workflow['description'],
                workflow['task_type'],
                workflow['status'],
                workflow['current_step'],
                workflow['priority'],
                workflow['created_at'],
                json.dumps(workflow['steps']),
                json.dumps(workflow['metadata']),
                json.dumps(workflow['execution_log']),
                json.dumps(workflow['rollback_data']) if workflow.get('rollback_data') else None
            ))
            conn.commit()
        return workflow['id']

    def update_workflow_status(self, workflow_id: str, status: str, current_step: int = None):
        with self._get_connection() as conn:
            if current_step is not None:
                conn.execute('''
                    UPDATE workflows 
                    SET status = ?, current_step = ?
                    WHERE id = ?
                ''', (status, current_step, workflow_id))
            else:
                conn.execute('''
                    UPDATE workflows 
                    SET status = ?
                    WHERE id = ?
                ''', (status, workflow_id))
            conn.commit()

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute('SELECT * FROM workflows WHERE id = ?', (workflow_id,)).fetchone()
            if row:
                return self._row_to_dict(row)
            return None

    def get_all_workflows(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute('SELECT * FROM workflows ORDER BY created_at DESC').fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        data = dict(row)
        # Parse JSON fields
        for field in ['steps', 'metadata', 'execution_log', 'rollback_data']:
            if data.get(field):
                data[field] = json.loads(data[field])
        return data