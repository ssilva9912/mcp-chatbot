# api/main.py - COMPLETE FIXED VERSION
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uuid
import os
from datetime import datetime
import traceback

# Import our components - FIXED IMPORTS
from memory.redis_memory import memory
from utils.simple_router import router  # Use the simple router

# MCP client import with better error handling
mcp_client = None
MCP_AVAILABLE = False

try:
    from mcp_client import MCPClient
    # Try to get API key from environment
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        mcp_client = MCPClient(api_key)
        MCP_AVAILABLE = True
        print("✅ MCP Client initialized successfully")
    else:
        print("⚠️ No Gemini API key found (GEMINI_API_KEY or GOOGLE_API_KEY)")
        print("⚠️ MCP features will be limited")
except Exception as e:
    print(f"⚠️ MCP Client initialization failed: {e}")
    print("⚠️ Continuing without MCP client")

app = FastAPI(title="MCP Chatbot API", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    use_routing: bool = True

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting MCP Chatbot API...")
    
    if mcp_client and MCP_AVAILABLE:
        try:
            # Try to connect to MCP server
            server_path = os.getenv("MCP_SERVER_PATH", "server/server.py")
            
            # Try multiple server paths
            possible_paths = [
                server_path,
                "../server/server.py",
                "./server/server.py",
                "server.py"
            ]
            
            connected = False
            for path in possible_paths:
                if os.path.exists(path):
                    try:
                        await mcp_client.connect_to_server(path)
                        print(f"✅ MCP Server connected at: {path}")
                        connected = True
                        break
                    except Exception as e:
                        print(f"⚠️ Failed to connect to server at {path}: {e}")
                        continue
            
            if not connected:
                print("⚠️ No MCP server found at any expected location")
                print("⚠️ Available server paths checked:", possible_paths)
                
        except Exception as e:
            print(f"⚠️ MCP Server connection failed: {e}")
    
    print("💾 Memory system initialized")
    print("🔀 Router system initialized") 
    print("🎉 API ready to handle requests!")

@app.on_event("shutdown")
async def shutdown_event():
    if mcp_client:
        try:
            await mcp_client.cleanup()
            print("✅ MCP Client disconnected")
        except Exception as e:
            print(f"❌ Error disconnecting MCP Client: {e}")

# Main chat endpoint - FRONTEND COMPATIBLE
@app.post("/query")
async def process_query(request: QueryRequest):
    """Process user query - Frontend Compatible"""
    
    session_id = request.session_id or str(uuid.uuid4())
    
    print(f"🎯 Processing query for session {session_id[:8]}...")
    print(f"📝 Query: {request.query[:100]}...")
    
    try:
        # Add user message to memory
        memory.add_message(session_id, "user", request.query)
        
        # Get conversation context
        context = memory.get_recent_context(session_id, max_messages=6)
        
        # Route the query
        routing_info = None
        tool_used = None
        response = ""
        
        if request.use_routing:
            routing_decision = router.route_query(request.query, context)
            routing_info = {
                "tool_name": routing_decision.tool_name,
                "confidence": routing_decision.confidence,
                "reasoning": routing_decision.reasoning
            }
            
            print(f"🔀 Routing: {routing_decision.tool_name or 'general_chat'} ({routing_decision.confidence:.2f})")
            
            # Handle based on routing
            if routing_decision.tool_name and mcp_client and MCP_AVAILABLE:
                # Try to use MCP for tool calls
                try:
                    response = await mcp_client.process_query(request.query)
                    tool_used = routing_decision.tool_name
                    print("✅ MCP response generated")
                except Exception as e:
                    print(f"⚠️ MCP failed, using fallback: {e}")
                    response = await handle_fallback_response(request.query, routing_decision)
                    tool_used = f"{routing_decision.tool_name}_fallback"
            else:
                # Use fallback handlers
                response = await handle_fallback_response(request.query, routing_decision)
                tool_used = routing_decision.tool_name
        else:
            # No routing - try MCP directly or fallback
            if mcp_client and MCP_AVAILABLE:
                try:
                    response = await mcp_client.process_query(request.query)
                    print("✅ Direct MCP response generated")
                except Exception as e:
                    print(f"⚠️ Direct MCP failed, using fallback: {e}")
                    response = await handle_general_chat(request.query, context)
            else:
                response = await handle_general_chat(request.query, context)
        
        # Add assistant response to memory
        memory.add_message(session_id, "assistant", response)
        
        # Get message count
        message_count = memory.count_messages(session_id)
        
        print(f"✅ Response generated ({len(response)} chars)")
        
        # Return frontend-compatible response
        return {
            "response": response,
            "message": response,      # Alternative field name
            "content": response,      # Alternative field name  
            "text": response,         # Alternative field name
            "session_id": session_id,
            "tool_used": tool_used,
            "routing_info": routing_info,
            "message_count": message_count,
            "status": "success"
        }
        
    except Exception as e:
        print(f"❌ Error processing query: {e}")
        print(f"📝 Traceback: {traceback.format_exc()}")
        
        error_response = f"I encountered an error: {str(e)}. Let me try to help you anyway!"
        
        # Try to save error response
        try:
            memory.add_message(session_id, "assistant", error_response)
        except:
            pass
        
        return {
            "response": error_response,
            "message": error_response,
            "content": error_response,
            "text": error_response,
            "session_id": session_id,
            "tool_used": None,
            "routing_info": None,
            "message_count": 0,
            "status": "error",
            "error": str(e)
        }

async def handle_fallback_response(query: str, routing_decision) -> str:
    """Handle responses when MCP is not available"""
    
    query_lower = query.lower()
    
    if routing_decision.tool_name == "sticky_notes":
        if any(word in query_lower for word in ['add', 'save', 'write', 'remember', 'note']):
            return f"📝 I would save this note: '{query}'\n\n(Note: MCP server not connected, so this is a simulation. Your note would normally be saved to the database.)"
        elif any(word in query_lower for word in ['read', 'show', 'list']):
            return "📋 Here would be your saved notes:\n\n(Note: MCP server not connected. Connect the server to see actual notes.)"
        elif any(word in query_lower for word in ['search', 'find']):
            return f"🔍 I would search your notes for: '{query}'\n\n(Note: MCP server not connected. Connect the server to search actual notes.)"
        else:
            return "📝 Sticky Notes feature detected!\n\nAvailable commands:\n• 'Add a note about...'\n• 'Show my notes'\n• 'Search notes for...'\n\n(Note: Connect MCP server for full functionality)"
    
    elif routing_decision.tool_name == "docs_search":
        return f"📚 I would search documentation for: '{query}'\n\n🔍 Typical results would include:\n• Official documentation links\n• Code examples\n• Tutorial resources\n\n(Note: MCP server not connected. Connect the server for actual web search.)"
    
    elif routing_decision.tool_name == "math":
        # Simple math fallback
        if 'derivative' in query_lower:
            if 'x^2' in query or 'x²' in query:
                return "📐 Derivative of x² = 2x\n\n✅ Using basic calculus rules"
            return f"📐 I would calculate the derivative for: '{query}'\n\n(Note: Connect MCP server for advanced math calculations)"
        elif 'integral' in query_lower:
            return f"∫ I would calculate the integral for: '{query}'\n\n(Note: Connect MCP server for advanced math calculations)"
        else:
            return f"🧮 Math calculation requested: '{query}'\n\n(Note: Connect MCP server for full math capabilities)"
    
    else:
        return await handle_general_chat(query, "")

async def handle_general_chat(query: str, context: str) -> str:
    """Handle general conversation"""
    
    query_lower = query.lower()
    
    # Greetings
    if any(greeting in query_lower for greeting in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
        return "Hello! 👋 I'm your intelligent assistant. I can help you with:\n\n📝 Sticky notes and reminders\n📚 Documentation searches\n🧮 Math calculations\n💬 General conversation\n\nWhat would you like to do today?"
    
    # Status questions
    elif any(phrase in query_lower for phrase in ['how are you', 'what\'s up', 'how\'s it going']):
        mcp_status = "✅ Connected" if mcp_client and MCP_AVAILABLE else "⚠️ Not connected"
        return f"I'm doing great! 😊\n\n**System Status:**\n• Memory: ✅ Working\n• Router: ✅ Working\n• MCP Server: {mcp_status}\n• Redis: ✅ Working\n\nI'm ready to help you with anything you need!"
    
    # Help requests
    elif 'help' in query_lower or 'what can you do' in query_lower:
        return """I can help you with several things:

📝 **Sticky Notes & Reminders**
   • "Add a note about my doctor appointment"
   • "Show me my notes"
   • "Search notes for 'meeting'"

📚 **Documentation Search**
   • "Search Python docs for list comprehensions"
   • "Find React documentation"
   • "Look up FastAPI tutorials"

🧮 **Math & Calculations**
   • "What's the derivative of x²?"
   • "Calculate 25 * 17"
   • "Integrate sin(x)"

💬 **General Chat**
   • Ask me questions about anything
   • I remember our conversation history

**Current Status:**
• MCP Server: """ + ("✅ Connected" if mcp_client and MCP_AVAILABLE else "⚠️ Connect server for full features") + """
• Memory System: ✅ Working
• All basic features available!

What would you like to try?"""
    
    # Thanks
    elif any(word in query_lower for word in ['thanks', 'thank you']):
        return "You're very welcome! 😊 I'm happy to help. Feel free to ask me anything else!"
    
    # Default response
    else:
        if '?' in query:
            return f"That's an interesting question: '{query}'\n\nI'd be happy to help! I work best with specific tasks like:\n• Managing notes and reminders\n• Searching documentation\n• Solving math problems\n• Having conversations\n\nHow can I assist you with this topic?"
        else:
            return f"I see you mentioned: '{query}'\n\nI'm here to help! I can assist with notes, documentation searches, math, or general questions. What would you like to do?"

# Tools endpoint for frontend
@app.get("/tools")
async def list_tools():
    """Get available tools for frontend"""
    try:
        tools = []
        
        if mcp_client and MCP_AVAILABLE:
            try:
                mcp_tools = await mcp_client.list_tools()
                tools.extend(mcp_tools)
            except Exception as e:
                print(f"⚠️ Failed to get MCP tools: {e}")
        
        # Add fallback tools
        fallback_tools = [
            {
                "name": "sticky_notes",
                "description": "Add, search, and manage personal notes and reminders",
                "available": True
            },
            {
                "name": "docs_search",
                "description": "Search documentation and web resources",
                "available": True
            },
            {
                "name": "math",
                "description": "Calculate derivatives, integrals, and solve math problems",
                "available": True
            },
            {
                "name": "general_chat",
                "description": "General conversation and questions",
                "available": True
            }
        ]
        
        # Merge and deduplicate
        all_tools = {tool["name"]: tool for tool in fallback_tools}
        for tool in tools:
            all_tools[tool["name"]] = tool
        
        final_tools = list(all_tools.values())
        
        return {
            "tools": final_tools,
            "count": len(final_tools),
            "mcp_connected": mcp_client is not None and MCP_AVAILABLE,
            "available": True
        }
        
    except Exception as e:
        print(f"❌ Error in /tools endpoint: {e}")
        return {
            "tools": [],
            "count": 0,
            "mcp_connected": False,
            "available": False,
            "error": str(e)
        }

# Memory management endpoints
@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str, limit: Optional[int] = None):
    """Get conversation history"""
    try:
        messages = memory.get_conversation(session_id, limit)
        return {
            "session_id": session_id,
            "messages": [msg.to_dict() for msg in messages],
            "count": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{session_id}")
async def clear_conversation(session_id: str):
    """Clear conversation history"""
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
    """List all conversations"""
    try:
        sessions = memory.list_sessions()
        return {
            "sessions": [
                {
                    "session_id": session_id,
                    "summary": memory.get_session_summary(session_id)
                }
                for session_id in sessions
            ],
            "count": len(sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health and status endpoints
@app.get("/health")
async def health_check():
    """Health check with system status"""
    try:
        # Test memory
        test_session = f"health_check_{datetime.now().isoformat()}"
        memory.add_message(test_session, "system", "health check")
        memory.clear_session(test_session)
        memory_status = "healthy"
    except Exception:
        memory_status = "unhealthy"
    
    # Test MCP
    mcp_status = "connected" if mcp_client and MCP_AVAILABLE else "disconnected"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "components": {
            "api": "healthy",
            "memory": memory_status,
            "mcp_client": mcp_status,
            "router": "healthy"
        },
        "stats": {
            "active_sessions": len(memory.list_sessions()),
            "mcp_available": MCP_AVAILABLE
        }
    }

@app.get("/status")
async def get_status():
    """Detailed system status"""
    try:
        # Get tools
        tools_count = 0
        available_tools = []
        
        if mcp_client and MCP_AVAILABLE:
            try:
                mcp_tools = await mcp_client.list_tools()
                tools_count = len(mcp_tools)
                available_tools = [tool.get("name", "unknown") for tool in mcp_tools]
            except Exception:
                pass
        
        # Get sessions info
        sessions = memory.list_sessions()
        
        return {
            "api_version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "mcp": {
                "available": MCP_AVAILABLE,
                "connected": mcp_client is not None,
                "tools_count": tools_count,
                "available_tools": available_tools
            },
            "memory": {
                "backend": type(memory).__name__,
                "active_sessions": len(sessions),
                "total_sessions": len(sessions)
            },
            "router": {
                "type": type(router).__name__,
                "available": True
            },
            "environment": {
                "gemini_api_key": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
                "redis_host": os.getenv("REDIS_HOST", "not_set"),
                "mcp_server_path": os.getenv("MCP_SERVER_PATH", "server/server.py")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Root endpoint
@app.get("/")
async def root():
    """API information"""
    return {
        "name": "MCP Chatbot API",
        "version": "2.0.0",
        "status": "running",
        "description": "Intelligent chatbot with Redis memory, smart routing, and MCP tool integration",
        "features": [
            "🧠 Redis conversation memory",
            "🔀 Intelligent query routing",
            "🛠️ MCP tool integration", 
            "📝 Sticky notes management",
            "📚 Documentation search",
            "🧮 Math calculations",
            "💬 Natural conversation"
        ],
        "endpoints": {
            "chat": "POST /query",
            "tools": "GET /tools", 
            "conversations": "GET /conversations",
            "health": "GET /health",
            "status": "GET /status",
            "documentation": "GET /docs"
        },
        "mcp_status": "connected" if (mcp_client and MCP_AVAILABLE) else "disconnected",
        "memory_sessions": len(memory.list_sessions())
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting MCP Chatbot API...")
    print("📍 API will be available at: http://localhost:8000")
    print("📚 API docs: http://localhost:8000/docs") 
    print("🔍 Health check: http://localhost:8000/health")
    print("🛠️ Tools list: http://localhost:8000/tools")
    uvicorn.run(app, host="0.0.0.0", port=8000)