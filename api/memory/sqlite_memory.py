import sqlite3
import os
from typing import List, Dict

class SimpleMemory:
    def __init__(self, db_path="conversations.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT
            )
        """)
        self.conn.commit()

    def add_message(self, session_id: str, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, datetime('now'))",
            (session_id, role, content)
        )
        self.conn.commit()

    def get_conversation(self, session_id: str) -> List[Dict]:
        cur = self.conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        )
        return [dict(role=row[0], content=row[1], timestamp=row[2]) for row in cur.fetchall()]

    def clear_session(self, session_id: str):
        self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.conn.commit()
