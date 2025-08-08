"""
Fixed Session Management for MCP Chatbot
File: utils/session_manager.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

class SessionState(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSING = "closing"
    CLOSED = "closed"

@dataclass
class Session:
    id: str
    user_id: str
    created_at: datetime
    last_activity: datetime
    state: SessionState
    context: Dict[str, Any]
    message_count: int = 0
    timeout_minutes: int = 30

    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.now() - self.last_activity > timedelta(minutes=self.timeout_minutes)
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
        self.message_count += 1

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.cleanup_interval = 300  # 5 minutes
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start_cleanup_task(self):
        """Start the cleanup task - call this when event loop is available"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            print("🧹 Session cleanup task started")
    
    async def stop_cleanup_task(self):
        """Stop the cleanup task"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            print("🛑 Session cleanup task stopped")
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                cleaned = self.cleanup_expired_sessions()
                if cleaned > 0:
                    print(f"🧹 Cleaned up {cleaned} expired sessions")
        except asyncio.CancelledError:
            print("🛑 Cleanup loop cancelled")
            raise
        except Exception as e:
            print(f"❌ Error in cleanup loop: {e}")
    
    def create_session(self, user_id: str) -> str:
        """Create a new session"""
        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            user_id=user_id,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state=SessionState.ACTIVE,
            context={}
        )
        self.sessions[session_id] = session
        print(f"✅ Created session {session_id[:8]}... for user {user_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        return self.sessions.get(session_id)
    
    def close_session(self, session_id: str, reason: str = "user_requested") -> bool:
        """Close a specific session"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.state = SessionState.CLOSING
        
        # Cleanup session data
        session.context.clear()
        
        # Log closure
        print(f"🚪 Session {session_id[:8]}... closed. Reason: {reason}")
        print(f"📊 Session stats: {session.message_count} messages, "
              f"duration: {datetime.now() - session.created_at}")
        
        # Mark as closed
        session.state = SessionState.CLOSED
        
        # Remove from active sessions
        del self.sessions[session_id]
        return True
    
    def close_user_sessions(self, user_id: str) -> int:
        """Close all sessions for a user"""
        closed_count = 0
        sessions_to_close = [
            sid for sid, session in self.sessions.items() 
            if session.user_id == user_id
        ]
        
        for session_id in sessions_to_close:
            if self.close_session(session_id, "user_logout"):
                closed_count += 1
        
        return closed_count
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions"""
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if session.is_expired()
        ]
        
        closed_count = 0
        for session_id in expired_sessions:
            if self.close_session(session_id, "expired"):
                closed_count += 1
        
        return closed_count
    
    def get_session_count(self) -> int:
        """Get total number of active sessions"""
        return len(self.sessions)
    
    def get_user_sessions(self, user_id: str) -> list:
        """Get all session IDs for a user"""
        return [
            session.id for session in self.sessions.values()
            if session.user_id == user_id
        ]