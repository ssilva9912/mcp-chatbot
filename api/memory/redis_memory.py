# api/conversations/redis_memory.py
import redis
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from dotenv import load_dotenv


load_dotenv()

@dataclass
class Message:
    role: str      # "user" or "assistant"
    content: str   # The message text
    timestamp: str # When it was sent
    session_id: str # Which conversation
    message_id: str # Unique message identifier
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict):
        return cls(**data)

class RedisMemory:
    """Redis-based conversation memory for production scalability"""
    
    def __init__(self):
        # Redis connection settings
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)
        self.redis_db = int(os.getenv("REDIS_DB", "0"))
        
        # Connect to Redis
        self.redis_client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            db=self.redis_db,
            decode_responses=True  # Automatically decode bytes to strings
        )
        
        # Test connection
        try:
            self.redis_client.ping()
            print(f"✅ Redis connected successfully at {self.redis_host}:{self.redis_port}")
        except redis.ConnectionError as e:
            print(f"❌ Redis connection failed: {e}")
            raise
    
    def _get_session_key(self, session_id: str) -> str:
        """Generate Redis key for session messages"""
        return f"chat:session:{session_id}:messages"
    
    def _get_sessions_key(self) -> str:
        """Generate Redis key for session index"""
        return "chat:sessions"
    
    def _get_session_meta_key(self, session_id: str) -> str:
        """Generate Redis key for session metadata"""
        return f"chat:session:{session_id}:meta"
    
    def add_message(self, session_id: str, role: str, content: str, tool_calls: Optional[List[Dict]] = None) -> bool:
        """Add a message to the conversation"""
        try:
            timestamp = datetime.now().isoformat()
            message_id = f"{session_id}:{timestamp}:{role}"
            
            message = Message(
                role=role,
                content=content,
                timestamp=timestamp,
                session_id=session_id,
                message_id=message_id
            )
            
            # Add tool calls if provided
            message_data = message.to_dict()
            if tool_calls:
                message_data['tool_calls'] = tool_calls
            
            # Store message in Redis list (ordered by time)
            session_key = self._get_session_key(session_id)
            self.redis_client.lpush(session_key, json.dumps(message_data))
            
            # Update session index
            sessions_key = self._get_sessions_key()
            self.redis_client.sadd(sessions_key, session_id)
            
            # Update session metadata
            meta_key = self._get_session_meta_key(session_id)
            self.redis_client.hset(meta_key, mapping={
                "last_activity": timestamp,
                "message_count": self.redis_client.llen(session_key)
            })
            
            # Set expiration (optional - 30 days default)
            expiry_days = int(os.getenv("SESSION_EXPIRY_DAYS", "30"))
            self.redis_client.expire(session_key, expiry_days * 24 * 3600)
            self.redis_client.expire(meta_key, expiry_days * 24 * 3600)
            
            print(f"💬 Added {role} message to Redis session {session_id[:8]}...")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add message to Redis: {e}")
            return False
    
    def get_conversation(self, session_id: str, limit: Optional[int] = 50) -> List[Message]:
        """Get messages for a session (most recent first, then reversed for chronological order)"""
        try:
            session_key = self._get_session_key(session_id)
            
            # Get messages from Redis list
            raw_messages = self.redis_client.lrange(session_key, 0, limit - 1 if limit else -1)
            
            # Parse and convert to Message objects
            messages = []
            for raw_msg in reversed(raw_messages):  # Reverse to get chronological order
                try:
                    msg_data = json.loads(raw_msg)
                    message = Message.from_dict({
                        k: v for k, v in msg_data.items() 
                        if k in ['role', 'content', 'timestamp', 'session_id', 'message_id']
                    })
                    messages.append(message)
                except json.JSONDecodeError:
                    print(f"⚠️ Skipping corrupted message in session {session_id}")
                    continue
            
            print(f"📖 Retrieved {len(messages)} messages from Redis session {session_id[:8]}...")
            return messages
            
        except Exception as e:
            print(f"❌ Failed to get conversation from Redis: {e}")
            return []
    
    def get_recent_context(self, session_id: str, max_messages: int = 10) -> str:
        """Get recent conversation as formatted string for AI context"""
        messages = self.get_conversation(session_id, limit=max_messages)
        
        if not messages:
            return ""
        
        context_lines = []
        for msg in messages[-max_messages:]:  # Get most recent messages
            prefix = "Human: " if msg.role == "user" else "Assistant: "
            context_lines.append(f"{prefix}{msg.content}")
        
        return "\n".join(context_lines)
    
    def count_messages(self, session_id: str) -> int:
        """Count messages in a session"""
        try:
            session_key = self._get_session_key(session_id)
            count = self.redis_client.llen(session_key)
            return count
        except Exception as e:
            print(f"❌ Failed to count messages in Redis: {e}")
            return 0
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages for a session"""
        try:
            session_key = self._get_session_key(session_id)
            meta_key = self._get_session_meta_key(session_id)
            sessions_key = self._get_sessions_key()
            
            # Delete session data
            deleted_messages = self.redis_client.delete(session_key)
            self.redis_client.delete(meta_key)
            self.redis_client.srem(sessions_key, session_id)
            
            print(f"🗑️ Cleared session {session_id[:8]} from Redis...")
            return True
            
        except Exception as e:
            print(f"❌ Failed to clear session from Redis: {e}")
            return False
    
    def list_sessions(self) -> List[str]:
        """Get all session IDs"""
        try:
            sessions_key = self._get_sessions_key()
            sessions = list(self.redis_client.smembers(sessions_key))
            
            # Sort by last activity (newest first)
            session_data = []
            for session_id in sessions:
                meta_key = self._get_session_meta_key(session_id)
                last_activity = self.redis_client.hget(meta_key, "last_activity")
                if last_activity:
                    session_data.append((session_id, last_activity))
            
            # Sort by timestamp and return session IDs
            sorted_sessions = sorted(session_data, key=lambda x: x[1], reverse=True)
            result = [session_id for session_id, _ in sorted_sessions]
            
            print(f"📋 Found {len(result)} sessions in Redis")
            return result
            
        except Exception as e:
            print(f"❌ Failed to list sessions from Redis: {e}")
            return []
    
    def get_session_summary(self, session_id: str) -> Dict:
        """Get summary info about a session"""
        try:
            meta_key = self._get_session_meta_key(session_id)
            meta_data = self.redis_client.hgetall(meta_key)
            
            message_count = int(meta_data.get("message_count", 0))
            last_activity = meta_data.get("last_activity")
            
            return {
                "session_id": session_id,
                "message_count": message_count,
                "last_activity": last_activity,
                "has_messages": message_count > 0,
                "storage_backend": "Redis"
            }
            
        except Exception as e:
            print(f"❌ Failed to get session summary from Redis: {e}")
            return {
                "session_id": session_id,
                "message_count": 0,
                "last_activity": None,
                "has_messages": False,
                "storage_backend": "Redis",
                "error": str(e)
            }
    
    def health_check(self) -> Dict:
        """Check Redis connection and get stats"""
        try:
            # Test connection
            self.redis_client.ping()
            
            # Get Redis info
            info = self.redis_client.info()
            sessions_count = self.redis_client.scard(self._get_sessions_key())
            
            return {
                "status": "healthy",
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human"),
                "total_sessions": sessions_count,
                "uptime_seconds": info.get("uptime_in_seconds")
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

# Create global memory instance
try:
    memory = RedisMemory()
except Exception as e:
    print(f"⚠️ Redis not available, falling back to SQLite: {e}")
    # Fallback to SQLite if Redis is not available
    from .sqlite_memory import SimpleMemory
    memory = SimpleMemory()

if __name__ == "__main__":
    print("🧪 Testing Redis memory system...")
    
    try:
        # Test basic functionality
        test_session = "test_redis_session"
        
        print("Testing add_message...")
        memory.add_message(test_session, "user", "Hello Redis!")
        memory.add_message(test_session, "assistant", "Hi there! Redis is working!")
        
        print("Testing get_conversation...")
        messages = memory.get_conversation(test_session)
        for msg in messages:
            print(f"  {msg.role}: {msg.content}")
        
        print("Testing get_context...")
        context = memory.get_recent_context(test_session)
        print(f"Context:\n{context}")
        
        print("Testing session summary...")
        summary = memory.get_session_summary(test_session)
        print(f"Summary: {summary}")
        
        print("Testing health check...")
        health = memory.health_check()
        print(f"Health: {health}")
        
        print("✅ All Redis tests passed!")
        
    except Exception as e:
        print(f"❌ Redis test failed: {e}")
        print("Make sure Redis is running: docker run -d -p 6379:6379 redis:alpine")