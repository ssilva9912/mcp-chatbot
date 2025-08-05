# api/main.py - Updated with conversation memory and auto-routing
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uuid
import os
from datetime import datetime

# Import our new components
from conversations.memory import memory
from utils.router import router

# Import existing MCP client (assuming you have this)
try:
    from client import MCPClient
    MCP_AVAILABLE = True
except ImportError:
    print("⚠️  MCP Client not found - running in demo mode")
    MCP_AVAILABLE = False

app = FastAPI(title="MCP Chatbot API with Memory & Routing", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MCP Client if available
mcp_client = None
if MCP_AVAILABLE:
    mcp_client = MCPClient()

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    use_routing: bool = True

class QueryResponse(BaseModel):
    response: str
    session_id: str
    tool_used: Optional[str] = None
    routing_info: Optional[Dict] = None
    message_count: int = 0

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    print("🚀 Starting MCP Chatbot API...")
    
    if mcp_client:
        try:
            await mcp_client.connect()
            print("✅ MCP Client connected successfully")
        except Exception as e:
            print(f"⚠️  MCP Client connection failed: {e}")
    
    print("💾 Memory system initialized")
    print("🔀 Router system initialized")
    print("🎉 API ready to handle requests!")

@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup on shutdown"""
    if mcp_client:
        try:
            await mcp_client.disconnect()
            print("✅ MCP Client disconnected")
        except Exception as e:
            print(f"❌ Error disconnecting MCP Client: {e}")

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process user query with conversation memory and auto-routing"""
    
    # Generate session ID if not provided
    session_id = request.session_id or str(uuid.uuid4())
    
    print(f"🎯 Processing query for session {session_id[:8]}...")
    print(f"📝 Query: {request.query[:100]}...")
    
    try:
        # Step 1: Add user message to memory
        memory.add_message(session_id, "user", request.query)
        
        # Step 2: Get conversation context for AI
        context = memory.get_recent_context(session_id, max_messages=6)
        
        # Step 3: Route the query (if enabled)
        routing_info = None
        tool_used = None
        
        if request.use_routing:
            routing_decision = router.route_query(request.query, context)
            routing_info = {
                "tool_name": routing_decision.tool_name,
                "confidence": routing_decision.confidence,
                "reasoning": routing_decision.reasoning
            }
            
            print(f"🔀 Routing decision: {routing_decision.tool_name or 'general_chat'} ({routing_decision.confidence:.2f})")
            
            # Step 4: Generate response based on routing
            if routing_decision.tool_name:
                response = await handle_tool_call(routing_decision.tool_name, request.query, context, session_id)
                tool_used = routing_decision.tool_name
            else:
                response = await handle_general_chat(request.query, context, session_id)
        else:
            # No routing - default to general chat
            response = await handle_general_chat(request.query, context, session_id)
        
        # Step 5: Add assistant response to memory
        memory.add_message(session_id, "assistant", response)
        
        # Step 6: Get updated message count
        message_count = memory.count_messages(session_id)
        
        print(f"✅ Response generated ({len(response)} chars)")
        
        return QueryResponse(
            response=response,
            session_id=session_id,
            tool_used=tool_used,
            routing_info=routing_info,
            message_count=message_count
        )
        
    except Exception as e:
        print(f"❌ Error processing query: {e}")
        # Still add error info to memory for debugging
        error_msg = f"I encountered an error: {str(e)}"
        memory.add_message(session_id, "assistant", error_msg)
        
        raise HTTPException(status_code=500, detail=str(e))

async def handle_general_chat(query: str, context: str, session_id: str) -> str:
    """Handle general conversation"""
    
    print("💬 Handling as general chat...")
    
    # Build a context-aware prompt
    if context:
        enhanced_query = f"""Previous conversation:
{context}

Current user message: {query}

Please respond naturally, taking into account our conversation history."""
    else:
        enhanced_query = query
    
    # Try to use MCP chat tool if available
    if mcp_client:
        try:
            result = await mcp_client.call_tool("chat", {"message": enhanced_query})
            return result.get("response", "I'm not sure how to respond to that.")
        except Exception as e:
            print(f"⚠️  MCP chat tool failed: {e}")
    
    # Fallback responses based on query type
    query_lower = query.lower()
    
    if any(greeting in query_lower for greeting in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
        return "Hello! I'm your MCP-powered assistant. I can help you with notes, documentation searches, math problems, and general questions. What would you like to do?"
    
    elif any(question in query_lower for question in ['how are you', 'how do you do', 'what\'s up']):
        return "I'm doing well, thank you! I'm ready to help you with whatever you need. I can manage notes, search documentation, solve math problems, or just chat."
    
    elif 'help' in query_lower:
        return """I can help you with several things:

📝 **Sticky Notes**: "Add a note about the meeting" or "Show my notes"
📚 **Documentation**: "Search for Python tutorials" or "Find React documentation"  
🧮 **Math**: "What's the derivative of x²?" or "Calculate 15 * 23"
💬 **General Chat**: Ask me questions or just have a conversation!

What would you like to do?"""
    
    else:
        return f"I understand you're asking about that. While I'd love to give you a detailed response, I'm currently running in a simplified mode. You asked: '{query}' - could you try rephrasing or let me know if you'd like help with notes, documentation, or math?"

async def handle_tool_call(tool_name: str, query: str, context: str, session_id: str) -> str:
    """Handle specific tool calls based on routing"""
    
    print(f"🔧 Handling tool call: {tool_name}")
    
    try:
        if tool_name == "sticky_notes":
            return await handle_sticky_notes(query, context)
        elif tool_name == "docs_search":
            return await handle_docs_search(query, context)
        elif tool_name == "math":
            return await handle_math(query, context)
        else:
            return await handle_general_chat(query, context, session_id)
            
    except Exception as e:
        print(f"❌ Tool {tool_name} failed: {e}")
        return f"I tried to use the {tool_name} tool, but encountered an issue. Let me try to help you differently: {query}"

async def handle_sticky_notes(query: str, context: str) -> str:
    """Handle sticky notes operations"""
    
    query_lower = query.lower()
    
    # Determine what the user wants to do with notes
    if any(word in query_lower for word in ['add', 'save', 'write', 'create', 'note that', 'remember']):
        # Extract the note content
        note_content = query
        
        # Try to clean up the content by removing command words
        for phrase in ['add a note about', 'save a note about', 'write down', 'note that', 'remember that', 'remember to']:
            if phrase in query_lower:
                start_idx = query_lower.find(phrase) + len(phrase)
                note_content = query[start_idx:].strip()
                break
        
        if mcp_client:
            try:
                result = await mcp_client.call_tool("add_note", {"message": note_content})
                return f"📝 {result.get('response', 'Note saved successfully!')}"
            except Exception as e:
                print(f"⚠️  MCP add_note failed: {e}")
        
        return f"📝 I'd save this note for you: '{note_content}' (Note: MCP sticky notes tool not available)"
        
    elif any(word in query_lower for word in ['search', 'find', 'look for']):
        # Extract search term
        search_term = query
        for phrase in ['search for', 'find', 'look for', 'search my notes for']:
            if phrase in query_lower:
                start_idx = query_lower.find(phrase) + len(phrase)
                search_term = query[start_idx:].strip()
                break
        
        if mcp_client:
            try:
                result = await mcp_client.call_tool("search_notes", {"query": search_term})
                return f"🔍 {result.get('response', 'No matching notes found.')}"
            except Exception as e:
                print(f"⚠️  MCP search_notes failed: {e}")
        
        return f"🔍 I'd search your notes for: '{search_term}' (Note: MCP sticky notes tool not available)"
        
    elif any(word in query_lower for word in ['show', 'list', 'read', 'get', 'all notes']):
        if mcp_client:
            try:
                result = await mcp_client.call_tool("read_notes", {})
                return f"📋 {result.get('response', 'No notes available.')}"
            except Exception as e:
                print(f"⚠️  MCP read_notes failed: {e}")
        
        return "📋 I'd show you all your notes here (Note: MCP sticky notes tool not available)"
        
    else:
        # Default to showing notes
        return await handle_sticky_notes("show my notes", context)

async def handle_docs_search(query: str, context: str) -> str:
    """Handle documentation search"""
    
    if mcp_client:
        try:
            result = await mcp_client.call_tool("docs_search", {"query": query})
            return f"📚 {result.get('response', 'No documentation found.')}"
        except Exception as e:
            print(f"⚠️  MCP docs_search failed: {e}")
    
    return f"📚 I'd search documentation for: '{query}' (Note: MCP docs search tool not available)"

async def handle_math(query: str, context: str) -> str:
    """Handle math operations"""
    
    query_lower = query.lower()
    
    if 'derivative' in query_lower:
        # Try to extract function
        if mcp_client:
            try:
                # This is a simplified extraction - you might want to improve this
                import re
                func_match = re.search(r'of\s+([^\s,]+)', query)
                if func_match:
                    func = func_match.group(1)
                    result = await mcp_client.call_tool("derivative", {"function": func})
                    return f"📐 {result.get('response', 'Could not calculate derivative.')}"
            except Exception as e:
                print(f"⚠️  MCP derivative failed: {e}")
        
        return f"📐 I'd calculate the derivative for you: '{query}' (Note: MCP math tool not available)"
        
    elif 'integral' in query_lower:
        if mcp_client:
            try:
                import re
                func_match = re.search(r'of\s+([^\s,]+)', query)
                if func_match:
                    func = func_match.group(1)
                    result = await mcp_client.call_tool("integral", {"function": func})
                    return f"∫ {result.get('response', 'Could not calculate integral.')}"
            except Exception as e:
                print(f"⚠️  MCP integral failed: {e}")
        
        return f"∫ I'd calculate the integral for you: '{query}' (Note: MCP math tool not available)"
    
    else:
        # General math
        return f"🧮 I'd help with that math problem: '{query}' (Note: MCP math tool not available)"

# Memory and conversation management endpoints

@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str, limit: Optional[int] = None):
    """Get conversation history for a session"""
    try:
        messages = memory.get_conversation(session_id, limit)
        summary = memory.get_session_summary(session_id)
        
        return {
            "session_id": session_id,
            "messages": [msg.to_dict() for msg in messages],
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{session_id}")
async def clear_conversation(session_id: str):
    """Clear conversation history for a session"""
    try:
        success = memory.clear_session(session_id)
        if success:
            return {"message": f"Conversation {session_id} cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear conversation")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations")
async def list_conversations():
    """List all conversation sessions"""
    try:
        sessions = memory.list_sessions()
        return {
            "sessions": [
                {
                    "session_id": session_id,
                    "summary": memory.get_session_summary(session_id)
                }
                for session_id in sessions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# System status and health endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    mcp_status = "not_available"
    
    if mcp_client:
        try:
            await mcp_client.list_tools()
            mcp_status = "connected"
        except Exception:
            mcp_status = "disconnected"
    
    return {
        "status": "healthy",
        "mcp_client": mcp_status,
        "memory_sessions": len(memory.list_sessions()),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status")
async def get_status():
    """Get detailed system status"""
    try:
        tools = []
        if mcp_client:
            try:
                tools = await mcp_client.list_tools()
            except Exception:
                pass
        
        sessions = memory.list_sessions()
        
        return {
            "api_version": "2.0.0",
            "mcp_available": MCP_AVAILABLE,
            "mcp_tools": len(tools),
            "available_tools": [tool.get("name", "unknown") for tool in tools] if tools else [],
            "active_sessions": len(sessions),
            "router_type": type(router).__name__,
            "memory_backend": "SQLite",
            "database_file": memory.db_path,
            "environment": {
                "simple_router": os.getenv("USE_SIMPLE_ROUTER", "true").lower() == "true",
                "mcp_client_available": MCP_AVAILABLE
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Simple test endpoint
@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "message": "MCP Chatbot API with Memory & Routing",
        "version": "2.0.0",
        "endpoints": {
            "chat": "/query",
            "conversations": "/conversations",
            "health": "/health",
            "status": "/status"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting MCP Chatbot API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)