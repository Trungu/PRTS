import sqlite3
import json
from typing import List, Dict, Any
from datetime import datetime, timezone
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "tasks.db")

def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            importance INTEGER DEFAULT 3,
            duration_minutes INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            last_pinged_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Ensure table exists on import
init_db()

def add_tasks(user_id: int, tasks: List[Dict[str, Any]]):
    """Adds multiple tasks to the database."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()

    for task in tasks:
        conn.execute('''
            INSERT INTO tasks (user_id, title, description, importance, duration_minutes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            task.get("title", "Untitled Task"),
            task.get("description", ""),
            task.get("importance", 3),
            task.get("duration_minutes", 0),
            "pending",
            now
        ))
    conn.commit()
    conn.close()

def get_pending_tasks(user_id: int) -> List[sqlite3.Row]:
    """Retrieves all pending tasks for a specific user, ordered by importance (desc)."""
    conn = _get_connection()
    cursor = conn.execute('''
        SELECT * FROM tasks
        WHERE user_id = ? AND status = 'pending'
        ORDER BY importance DESC, created_at ASC
    ''', (user_id,))
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def complete_task(task_id: int, user_id: int):
    """Marks a task as completed."""
    conn = _get_connection()
    conn.execute('''
        UPDATE tasks SET status = 'completed'
        WHERE id = ? AND user_id = ?
    ''', (task_id, user_id))
    conn.commit()
    conn.close()

def update_last_pinged(task_id: int):
    """Updates the last_pinged_at timestamp."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute('''
        UPDATE tasks SET last_pinged_at = ?
        WHERE id = ?
    ''', (now, task_id))
    conn.commit()
    conn.close()

def get_tasks_to_ping(hours_since_creation: int = 24, hours_since_last_ping: int = 24) -> List[sqlite3.Row]:
    """Retrieves pending tasks that haven't been completed and need a reminder ping."""
    conn = _get_connection()
    # SQLite datetime functions can be tricky, so we'll fetch pending tasks and filter in Python
    # for simplicity and reliability across timezones.
    cursor = conn.execute('''
        SELECT * FROM tasks WHERE status = 'pending'
    ''')
    all_pending = cursor.fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    to_ping = []

    for task in all_pending:
        created_at = datetime.fromisoformat(task["created_at"])
        last_pinged = datetime.fromisoformat(task["last_pinged_at"]) if task["last_pinged_at"] else None

        # Has it been long enough since creation?
        if (now - created_at).total_seconds() > (hours_since_creation * 3600):
            # If never pinged, ping it. If pinged, check if enough time passed since last ping.
            if last_pinged is None or (now - last_pinged).total_seconds() > (hours_since_last_ping * 3600):
                to_ping.append(task)

    return to_ping
