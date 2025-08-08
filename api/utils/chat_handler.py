"""
Fixed Main Chat Handler that coordinates session management and prompt parsing
File: utils/chat_handler.py
"""

from typing import Dict, Any, Optional
from .session_manager import SessionManager, Session
from .prompt_parser import PromptParser, ParsedPrompt, PromptComplexity

class MCPChatHandler:
    """Main handler for MCP chat with session management and complex prompt handling"""
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.prompt_parser = PromptParser()
        self._initialized = False
    
    async def initialize(self):
        """Initialize the handler - call this when event loop is available"""
        if not self._initialized:
            await self.session_manager.start_cleanup_task()
            self._initialized = True
            print("✅ MCPChatHandler initialized with session management")
    
    async def shutdown(self):
        """Shutdown the handler"""
        if self._initialized:
            await self.session_manager.stop_cleanup_task()
            self._initialized = False
            print("🛑 MCPChatHandler shutdown")
    
    async def handle_message(self, user_id: str, session_id: str, message: str) -> Dict[str, Any]:
        """Handle incoming message with session management"""
        
        # Ensure handler is initialized
        if not self._initialized:
            await self.initialize()
        
        # Check for session control commands first
        if self.prompt_parser.is_session_command(message):
            return await self._handle_session_command(user_id, session_id, message)
        
        # Get or create session
        session = self.session_manager.get_session(session_id)
        if not session:
            session_id = self.session_manager.create_session(user_id)
            session = self.session_manager.get_session(session_id)
        
        # Update session activity
        session.update_activity()
        
        # Parse the prompt
        parsed_prompt = self.prompt_parser.parse_prompt(message)
        
        # Handle based on complexity
        response = await self._handle_by_complexity(session, parsed_prompt)
        
        return {
            "session_id": session_id,
            "user_id": user_id,
            "response": response,
            "prompt_analysis": {
                "complexity": parsed_prompt.complexity.value,
                "task_count": len(parsed_prompt.tasks),
                "requires_context": parsed_prompt.requires_session_context,
                "estimated_tokens": parsed_prompt.estimated_tokens
            },
            "session_info": {
                "message_count": session.message_count,
                "session_age": str(session.last_activity - session.created_at)
            }
        }
    
    async def _handle_session_command(self, user_id: str, session_id: str, message: str) -> Dict[str, Any]:
        """Handle session control commands"""
        message_lower = message.lower().strip()
        
        if any(cmd in message_lower for cmd in ["close", "end", "logout", "exit", "quit"]):
            closed = self.session_manager.close_session(session_id, "user_command")
            return {
                "session_id": session_id,
                "response": {
                    "type": "session_closed",
                    "message": "Session closed successfully" if closed else "Session not found",
                    "closed": closed
                },
                "prompt_analysis": {
                    "complexity": "simple",
                    "task_count": 1,
                    "requires_context": False
                }
            }
        
        return {
            "session_id": session_id,
            "response": {
                "type": "unknown_command",
                "message": "Unknown session command"
            }
        }
    
    async def _handle_by_complexity(self, session: Session, parsed_prompt: ParsedPrompt) -> Dict[str, Any]:
        """Handle prompt based on its complexity"""
        
        if parsed_prompt.complexity == PromptComplexity.SIMPLE:
            return await self._handle_simple_prompt(session, parsed_prompt)
        
        elif parsed_prompt.complexity == PromptComplexity.COMPOUND:
            return await self._handle_compound_prompt(session, parsed_prompt)
        
        else:  # COMPLEX
            return await self._handle_complex_prompt(session, parsed_prompt)
    
    async def _handle_simple_prompt(self, session: Session, parsed_prompt: ParsedPrompt) -> Dict[str, Any]:
        """Handle simple, single-task prompts"""
        task = parsed_prompt.tasks[0]
        
        # Store context for future reference
        session.context["last_task"] = task
        session.context["last_prompt_type"] = "simple"
        
        return {
            "type": "simple_response",
            "task": task,
            "strategy": "direct_response",
            "message": f"Processing {task['type']} task: {task['text'][:50]}..."
        }
    
    async def _handle_compound_prompt(self, session: Session, parsed_prompt: ParsedPrompt) -> Dict[str, Any]:
        """Handle related multi-task prompts"""
        
        # Store context
        session.context["last_tasks"] = parsed_prompt.tasks
        session.context["last_prompt_type"] = "compound"
        
        return {
            "type": "compound_response",
            "tasks": parsed_prompt.tasks,
            "strategy": "sequential_handling",
            "message": f"Processing {len(parsed_prompt.tasks)} related tasks sequentially",
            "note": "Handling related tasks in logical order"
        }
    
    async def _handle_complex_prompt(self, session: Session, parsed_prompt: ParsedPrompt) -> Dict[str, Any]:
        """Handle complex, unrelated multi-task prompts"""
        
        # Sort tasks by priority
        sorted_tasks = sorted(parsed_prompt.tasks, key=lambda x: x['priority'])
        
        # Store context
        session.context["last_tasks"] = sorted_tasks
        session.context["last_prompt_type"] = "complex"
        
        return {
            "type": "complex_response",
            "tasks": sorted_tasks,
            "strategy": "prioritized_handling",
            "message": f"Processing {len(parsed_prompt.tasks)} different tasks",
            "recommendation": "Complex request detected. Processing in priority order.",
            "note": "Consider breaking complex requests into separate messages for better results"
        }
    
    def close_session(self, session_id: str) -> bool:
        """Close a specific session"""
        return self.session_manager.close_session(session_id)
    
    def close_user_sessions(self, user_id: str) -> int:
        """Close all sessions for a user"""
        return self.session_manager.close_user_sessions(user_id)
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return None
        
        return {
            "id": session.id,
            "user_id": session.user_id,
            "state": session.state.value,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "message_count": session.message_count,
            "is_expired": session.is_expired(),
            "context_keys": list(session.context.keys())
        }
    
    def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        return self.session_manager.get_session_count()
    
    def cleanup_expired(self) -> int:
        """Manually trigger cleanup of expired sessions"""
        return self.session_manager.cleanup_expired_sessions()