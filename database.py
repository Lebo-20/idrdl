import sqlite3
import json
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="bot_data.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Table for processed drama IDs
            conn.execute("CREATE TABLE IF NOT EXISTS processed (book_id TEXT PRIMARY KEY)")
            
            # Table for tasks queue
            # Status: 0=Pending, 1=Processing, 2=Completed, 3=Failed
            # Priority: 1=Manual (High), 2=Auto (Low)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT UNIQUE,
                    title TEXT,
                    chat_id INTEGER,
                    priority INTEGER,
                    status INTEGER DEFAULT 0,
                    error_msg TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # Processed IDs management
    def is_processed(self, book_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM processed WHERE book_id = ?", (str(book_id),))
            return cursor.fetchone() is not None

    def add_processed(self, book_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO processed (book_id) VALUES (?)", (str(book_id),))
            conn.commit()

    # Task Queue management
    def add_task(self, book_id, title, chat_id, priority=2):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO tasks (book_id, title, chat_id, priority, status) 
                    VALUES (?, ?, ?, ?, 0)
                """, (str(book_id), title, chat_id, priority))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # Already in tasks table (could be pending, processing, or failed)
            return False

    def get_next_task(self):
        with sqlite3.connect(self.db_path) as conn:
            # Get highest priority (lowest number) first, then oldest created_at
            cursor = conn.execute("""
                SELECT id, book_id, title, chat_id, priority 
                FROM tasks 
                WHERE status = 0 
                ORDER BY priority ASC, created_at ASC 
                LIMIT 1
            """)
            return cursor.fetchone()

    def update_task_status(self, task_id, status, error_msg=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE tasks SET status = ?, error_msg = ? WHERE id = ?", (status, error_msg, task_id))
            conn.commit()

    def delete_task(self, task_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

    def get_queue_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 0").fetchone()[0]
            processing = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 1").fetchone()[0]
            return {"pending": pending, "processing": processing}

    def get_active_task_info(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT title FROM tasks WHERE status = 1 LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else "Idle"

    def reset_processing_tasks(self):
        """Reset any tasks stuck in 'Processing' status (e.g. after crash)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE tasks SET status = 0 WHERE status = 1")
            conn.commit()

db = Database()
