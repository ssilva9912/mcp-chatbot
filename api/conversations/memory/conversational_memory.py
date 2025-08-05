# api/conversations/memory.py
from typing import Dict, List, Optional
from datetime import datetime
import json
import sqlite3
import os
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    tool_calls: Optional[List[Dict]] = None
    
    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict):
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

class ConversationMemory:
    """Manages conversation history with optional persistence"""
    
    def __init__(self, use_persistence: bool = False, db_path: str = "conversations.db"):
        self.use_persistence = use_persistence
        self.db_path = db_path
        
        # In-memory storage (always used)
        self.conversations: Dict[str, List[Message]] = {}
        
        # Initialize database if persistence enabled
        if self.use_persistence:
            self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for conversation persistence"""
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tool_calls TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON conversations(session_id)")
    
    def add_message(self, session_id: str, role: str, content: str, tool_calls: Optional[List[Dict]] = None):
        """Add a message to the conversation"""
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            tool_calls=tool_calls
        )
        
        # Add to memory
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        self.conversations[session_id].append(message)
        
        # Persist if enabled
        if self.use_persistence:
            self._save_message_to_db(session_id, message)
    
    def _save_message_to_db(self, session_id: str, message: Message):
        """Save message to database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO conversations (session_id, role, content, timestamp, tool_calls)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                message.role,
                message.content,
                message.timestamp.isoformat(),
                json.dumps(message.tool_calls) if message.tool_calls else None
            ))
    
    def get_conversation(self, session_id: str, limit: Optional[int] = None) -> List[Message]:
        """Get conversation history for a session"""
        # Try memory first
        if session_id in self.conversations:
            messages = self.conversations[session_id]
            return messages[-limit:] if limit else messages
        
        # If not in memory and persistence enabled, load from DB
        if self.use_persistence:
            return self._load_conversation_from_db(session_id, limit)
        
        return []
    
    def _load_conversation_from_db(self, session_id: str, limit: Optional[int] = None) -> List[Message]:
        """Load conversation from database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT * FROM conversations 
                WHERE session_id = ? 
                ORDER BY timestamp ASC
            """
            if limit:
                query += f" LIMIT {limit}"
            
            cursor = conn.execute(query, (session_id,))
            rows = cursor.fetchall()
            
            messages = []
            for row in rows:
                tool_calls = json.loads(row['tool_calls']) if row['tool_calls'] else None
                message = Message(
                    role=row['role'],
                    content=row['content'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    tool_calls=tool_calls
                )
                messages.append(message)
            
            # Cache in memory
            self.conversations[session_id] = messages
            return messages
    
    def get_recent_context(self, session_id: str, max_messages: int = 10) -> str:
        """Get recent conversation context as formatted string"""
        messages = self.get_conversation(session_id, limit=max_messages)
        
        if not messages:
            return ""
        
        context_lines = []
        for msg in messages:
            prefix = "User: " if msg.role == "user" else "Assistant: "
            context_lines.append(f"{prefix}{msg.content}")
            
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    context_lines.append(f"  → Used tool: {tool_call.get('name', 'unknown')}")
        
        return "\n".join(context_lines)
    
    def clear_conversation(self, session_id: str):
        """Clear conversation history for a session"""
        if session_id in self.conversations:
            del self.conversations[session_id]
        
        if self.use_persistence:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
    
    def get_conversation_summary(self, session_id: str) -> Dict:
        """Get summary info about a conversation"""
        messages = self.get_conversation(session_id)
        
        if not messages:
            return {"message_count": 0, "first_message": None, "last_message": None}
        
        return {
            "message_count": len(messages),
            "first_message": messages[0].timestamp.isoformat(),
            "last_message": messages[-1].timestamp.isoformat(),
            "tools_used": list(set([
                tool['name'] for msg in messages 
                if msg.tool_calls 
                for tool in msg.tool_calls
            ]))
        }
    
    def list_sessions(self) -> List[str]:
        """List all session IDs"""
        sessions = set(self.conversations.keys())
        
        if self.use_persistence:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT DISTINCT session_id FROM conversations")
                db_sessions = {row[0] for row in cursor.fetchall()}
                sessions.update(db_sessions)
        
        return list(sessions)

# Singleton instance
memory = ConversationMemory(use_persistence=True)