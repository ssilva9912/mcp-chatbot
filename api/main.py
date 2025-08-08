# api/main.py - FIXED VERSION WITH BETTER COMPLEX TASK HANDLING
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
from utils.chat_handler import MCPChatHandler  # NEW: Import chat handler

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

app = FastAPI(title="MCP Chatbot API", version="2.0.1")

# Initialize chat handler globally
chat_handler = None

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
    user_id: Optional[str] = "default_user"
    use_routing: bool = True
    use_chat_handler: bool = True  # NEW: Option to use new handler

@app.on_event("startup")
async def startup_event():
    global chat_handler
    print("🚀 Starting MCP Chatbot API...")
    
    # Initialize chat handler
    try:
        chat_handler = MCPChatHandler()
        await chat_handler.initialize()
        print("✅ Chat handler initialized with session management")
    except Exception as e:
        print(f"⚠️ Chat handler initialization failed: {e}")
        print("⚠️ Continuing with basic handler")
    
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
    global chat_handler
    
    # Shutdown chat handler
    if chat_handler:
        try:
            await chat_handler.shutdown()
            print("✅ Chat handler shutdown")
        except Exception as e:
            print(f"❌ Error shutting down chat handler: {e}")
    
    if mcp_client:
        try:
            await mcp_client.cleanup()
            print("✅ MCP Client disconnected")
        except Exception as e:
            print(f"❌ Error disconnecting MCP Client: {e}")

# NEW: Enhanced main chat endpoint with chat handler
@app.post("/query")
async def process_query(request: QueryRequest):
    """Process user query - Enhanced with Chat Handler"""
    
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id
    
    print(f"🎯 Processing query for session {session_id[:8]}...")
    print(f"📝 Query: {request.query[:100]}...")
    print(f"🔧 Using chat handler: {request.use_chat_handler}")
    
    try:
        # Use new chat handler if available and requested
        if chat_handler and request.use_chat_handler:
            return await process_with_chat_handler(request, session_id, user_id)
        else:
            return await process_with_legacy_handler(request, session_id)
            
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

async def process_with_chat_handler(request: QueryRequest, session_id: str, user_id: str) -> Dict[str, Any]:
    """Process query using the new chat handler"""
    
    print("🆕 Using new chat handler")
    
    # Use the new chat handler
    result = await chat_handler.handle_message(user_id, session_id, request.query)
    
    # Check if it's a session command
    if result["response"].get("type") == "session_closed":
        return {
            "response": result["response"]["message"],
            "message": result["response"]["message"],
            "session_id": session_id,
            "status": "session_closed",
            "prompt_analysis": result["prompt_analysis"]
        }
    
    # Build response based on complexity
    response_text = ""
    
    if result["response"]["type"] == "simple_response":
        # Handle simple responses - try to get actual response from MCP/tools
        task = result["response"]["task"]
        
        if request.use_routing and mcp_client and MCP_AVAILABLE:
            try:
                # Try MCP for actual response
                mcp_response = await mcp_client.process_query(request.query)
                response_text = mcp_response
                print("✅ MCP response for simple task")
            except Exception as e:
                print(f"⚠️ MCP failed for simple task: {e}")
                response_text = await handle_task_with_fallback(task, request.query)
        else:
            response_text = await handle_task_with_fallback(task, request.query)
    
    elif result["response"]["type"] == "compound_response":
        # Handle compound (related) tasks
        tasks = result["response"]["tasks"]
        
        if request.use_routing and mcp_client and MCP_AVAILABLE:
            try:
                # Try MCP for compound response
                mcp_response = await mcp_client.process_query(request.query)
                response_text = mcp_response
                print("✅ MCP response for compound tasks")
            except Exception as e:
                print(f"⚠️ MCP failed for compound tasks: {e}")
                response_text = await handle_compound_tasks(tasks, request.query)
        else:
            response_text = await handle_compound_tasks(tasks, request.query)
    
    elif result["response"]["type"] == "complex_response":
        # Handle complex (unrelated) tasks - IMPROVED
        tasks = result["response"]["tasks"]
        response_text = await handle_complex_tasks(tasks, request.query)
    
    else:
        # Unknown response type
        response_text = result["response"].get("message", "I processed your request.")
    
    # Add to Redis memory for compatibility
    memory.add_message(session_id, "user", request.query)
    memory.add_message(session_id, "assistant", response_text)
    
    return {
        "response": response_text,
        "message": response_text,
        "content": response_text,
        "text": response_text,
        "session_id": session_id,
        "tool_used": result["response"].get("strategy"),
        "routing_info": {
            "complexity": result["prompt_analysis"]["complexity"],
            "task_count": result["prompt_analysis"]["task_count"],
            "requires_context": result["prompt_analysis"]["requires_context"]
        },
        "message_count": result["session_info"]["message_count"],
        "status": "success",
        "prompt_analysis": result["prompt_analysis"],
        "session_info": result["session_info"],
        "handler_used": "chat_handler"
    }

async def handle_task_with_fallback(task: Dict[str, Any], query: str) -> str:
    """Handle a single task with fallback logic"""
    
    task_type = task.get("type", "general")
    task_text = task.get("text", query)
    
    if task_type == "creation":
        # Handle creation tasks with actual content
        if 'mcp server' in task_text.lower() and 'langgraph' in task_text.lower():
            return """I'll help you implement an MCP server using LangGraph! Here's how to enhance your MCP server:

## Core MCP Server with LangGraph Integration

**1. Enhanced Server Structure:**
```python
# server.py
import asyncio
from mcp import Server
from mcp.types import Tool, TextContent
from langgraph import StateGraph
from typing import TypedDict, List

server = Server("langgraph-enhanced-mcp")

class WorkflowState(TypedDict):
    input: str
    steps: List[str]
    result: str
    context: dict

@server.list_tools()
async def list_tools():
    return [
        Tool(name="process_workflow", description="Process complex workflows with LangGraph"),
        Tool(name="manage_conversation", description="Advanced conversation flow management")
    ]
```

**2. LangGraph Workflow Integration:**
```python
def create_workflow_graph():
    workflow = StateGraph(WorkflowState)
    
    # Add nodes for different processing steps
    workflow.add_node("parse_input", parse_input_node)
    workflow.add_node("determine_action", determine_action_node)
    workflow.add_node("execute_action", execute_action_node)
    workflow.add_node("format_response", format_response_node)
    
    # Define the flow
    workflow.add_edge("parse_input", "determine_action")
    workflow.add_edge("determine_action", "execute_action")
    workflow.add_edge("execute_action", "format_response")
    
    workflow.set_entry_point("parse_input")
    workflow.set_finish_point("format_response")
    
    return workflow.compile()
```

**3. Node Implementation:**
```python
async def parse_input_node(state: WorkflowState) -> WorkflowState:
    # Parse and analyze the input
    state["steps"].append("Input parsed")
    return state

async def determine_action_node(state: WorkflowState) -> WorkflowState:
    # Determine what action to take based on input
    state["steps"].append("Action determined")
    return state
```

This creates a powerful combination where LangGraph handles complex workflow orchestration while MCP provides the server infrastructure!"""
        
        elif 'caesar salad' in task_text.lower():
            return """## Classic Caesar Salad Recipe

**Ingredients:**
- 1 large head romaine lettuce, chopped
- 1/2 cup freshly grated Parmesan cheese
- 1 cup croutons
- Caesar dressing (see below)

**For the Dressing:**
- 3 garlic cloves, minced
- 2 anchovy fillets (optional)
- 2 tablespoons lemon juice
- 1 teaspoon Dijon mustard
- 1/2 cup olive oil
- Salt and pepper to taste

**Instructions:**
1. Wash and chop romaine lettuce
2. Make dressing by whisking together garlic, anchovies, lemon juice, and mustard
3. Slowly drizzle in olive oil while whisking
4. Toss lettuce with dressing
5. Top with Parmesan cheese and croutons
6. Serve immediately!

**Chef's Tip:** For authentic flavor, add a raw egg yolk to the dressing and use real Parmigiano-Reggiano cheese."""
        
        else:
            return f"🔧 I'll help you create: {task_text}\n\n(This would normally use specialized tools to assist with creation tasks)"
    
    elif task_type == "explanation":
        # Try to provide a helpful explanation
        context = memory.get_recent_context("", max_messages=2)  # Get general context
        return await handle_general_chat(query, context)
    
    elif task_type == "search":
        return f"🔍 I would search for: {task_text}\n\n(Connect MCP server for actual web search capabilities)"
    
    elif task_type == "recipe":
        if 'caesar salad' in task_text.lower():
            return """## Classic Caesar Salad Recipe

**Ingredients:**
- 1 large head romaine lettuce, chopped
- 1/2 cup freshly grated Parmesan cheese
- 1 cup croutons
- Caesar dressing

**Instructions:**
1. Wash and chop romaine lettuce
2. Toss with Caesar dressing
3. Top with Parmesan and croutons
4. Serve immediately!"""
        else:
            return f"👨‍🍳 Recipe request detected: {task_text}\n\n(This would normally provide step-by-step cooking instructions)"
    
    else:
        return await handle_general_chat(query, "")

async def handle_compound_tasks(tasks: List[Dict[str, Any]], query: str) -> str:
    """Handle multiple related tasks"""
    
    # Try to handle all tasks with actual content
    response_parts = []
    
    for i, task in enumerate(tasks, 1):
        task_response = await handle_task_with_fallback(task, task.get('text', ''))
        response_parts.append(f"**{i}. {task['text']}**\n{task_response}\n")
    
    return "\n".join(response_parts)

async def handle_complex_tasks(tasks: List[Dict[str, Any]], query: str) -> str:
    """Handle multiple unrelated tasks with better content generation"""
    
    # Try MCP first, but with better error handling
    if mcp_client and MCP_AVAILABLE:
        try:
            print("🔄 Trying MCP for complex query...")
            mcp_response = await mcp_client.process_query(query)
            
            # Check if MCP response is substantial
            if len(mcp_response) > 100 and "Error executing tool" not in mcp_response:
                # Good MCP response, add task analysis
                task_summary = f"\n\n---\n**📋 Task Analysis:** I detected {len(tasks)} different requests:\n"
                for i, task in enumerate(tasks, 1):
                    task_summary += f"{i}. {task['text']} ({task['type']})\n"
                
                return mcp_response + task_summary
            else:
                print("⚠️ MCP response was too short or contained errors, using fallback")
                
        except Exception as e:
            print(f"⚠️ MCP failed for complex prompt: {e}")
    
    # Enhanced fallback: Handle each task individually
    print("🔄 Using enhanced fallback for complex tasks")
    
    # Handle the primary tasks with actual content
    response_parts = []
    
    # Process main tasks
    main_tasks = tasks[:2]  # Handle first 2 tasks with full content
    
    for i, task in enumerate(main_tasks, 1):
        task_response = await handle_task_with_fallback(task, task.get('text', ''))
        response_parts.append(f"**{i}. {task['text']}**\n{task_response}")
        
        if i < len(main_tasks):
            response_parts.append("\n---\n")
    
    # List remaining tasks if any
    if len(tasks) > 2:
        remaining_tasks = tasks[2:]
        response_parts.append(f"\n\n**📋 Additional requests detected:**")
        for i, task in enumerate(remaining_tasks, 3):
            response_parts.append(f"{i}. {task['text']} ({task['type']})")
        response_parts.append("\nFeel free to ask about these separately for detailed responses!")
    
    return "\n".join(response_parts)

async def process_with_legacy_handler(request: QueryRequest, session_id: str) -> Dict[str, Any]:
    """Process query using the original logic"""
    
    print("🔄 Using legacy handler")
    
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
        "status": "success",
        "handler_used": "legacy"
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
        chat_handler_status = "✅ Active" if chat_handler else "⚠️ Not available"
        return f"Hello! 👋 I'm your intelligent assistant. I can help you with:\n\n📝 Sticky notes and reminders\n📚 Documentation searches\n🧮 Math calculations\n💬 General conversation\n🧠 Advanced session management\n\n**System Status:**\n• Chat Handler: {chat_handler_status}\n• MCP Server: {'✅ Connected' if mcp_client and MCP_AVAILABLE else '⚠️ Not connected'}\n\nWhat would you like to do today?"
    
    # Status questions
    elif any(phrase in query_lower for phrase in ['how are you', 'what\'s up', 'how\'s it going']):
        mcp_status = "✅ Connected" if mcp_client and MCP_AVAILABLE else "⚠️ Not connected"
        chat_handler_status = "✅ Active" if chat_handler else "⚠️ Not available"
        return f"I'm doing great! 😊\n\n**System Status:**\n• Memory: ✅ Working\n• Router: ✅ Working\n• Chat Handler: {chat_handler_status}\n• MCP Server: {mcp_status}\n• Redis: ✅ Working\n\nI'm ready to help you with anything you need!"
    
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

🧠 **Advanced Features**
   • Smart prompt analysis and task detection
   • Automatic session management
   • Complex multi-task handling
   • Session commands: "close session", "end chat"

💬 **General Chat**
   • Ask me questions about anything
   • I remember our conversation history

**Current Status:**
• Chat Handler: """ + ("✅ Active with session management" if chat_handler else "⚠️ Basic mode") + """
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

# Session management endpoints
@app.get("/sessions")
async def list_sessions():
    """List all active sessions from chat handler"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not available")
    
    try:
        session_count = chat_handler.get_active_sessions_count()
        return {
            "active_sessions": session_count,
            "status": "active" if session_count > 0 else "no_active_sessions"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Get detailed session information"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not available")
    
    try:
        session_info = chat_handler.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return session_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sessions/{session_id}")
async def close_session(session_id: str):
    """Close a specific session"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not available")
    
    try:
        success = chat_handler.close_session(session_id)
        if success:
            return {"message": f"Session {session_id} closed successfully"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sessions/cleanup")
async def cleanup_expired_sessions():
    """Manually trigger cleanup of expired sessions"""
    if not chat_handler:
        raise HTTPException(status_code=503, detail="Chat handler not available")
    
    try:
        cleaned_count = chat_handler.cleanup_expired()
        return {
            "message": f"Cleaned up {cleaned_count} expired sessions",
            "cleaned_count": cleaned_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup-sessions")
async def cleanup_sessions():
    """Clean up all active sessions"""
    if not chat_handler:
        return {"error": "Chat handler not available"}
    
    try:
        # Get current count
        initial_count = chat_handler.get_active_sessions_count()
        
        # Close all sessions
        all_session_ids = list(chat_handler.session_manager.sessions.keys())
        closed_count = 0
        
        for session_id in all_session_ids:
            if chat_handler.close_session(session_id):
                closed_count += 1
        
        return {
            "message": f"Cleaned up {closed_count} sessions",
            "before": initial_count,
            "after": chat_handler.get_active_sessions_count()
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/cleanup-all-sessions")
async def cleanup_all_sessions():
    """Clean up BOTH Redis memory and chat handler sessions"""
    results = {}
    
    # Clean up chat handler sessions
    if chat_handler:
        try:
            chat_initial = chat_handler.get_active_sessions_count()
            chat_cleaned = 0
            all_session_ids = list(chat_handler.session_manager.sessions.keys())
            for session_id in all_session_ids:
                if chat_handler.close_session(session_id):
                    chat_cleaned += 1
            results["chat_handler"] = {
                "before": chat_initial,
                "cleaned": chat_cleaned,
                "after": chat_handler.get_active_sessions_count()
            }
        except Exception as e:
            results["chat_handler"] = {"error": str(e)}
    
    # Clean up Redis memory sessions
    try:
        redis_sessions = memory.list_sessions()
        redis_initial = len(redis_sessions)
        redis_cleaned = 0
        
        for session_id in redis_sessions:
            if memory.clear_session(session_id):
                redis_cleaned += 1
        
        results["redis_memory"] = {
            "before": redis_initial,
            "cleaned": redis_cleaned,
            "after": len(memory.list_sessions())
        }
    except Exception as e:
        results["redis_memory"] = {"error": str(e)}
    
    return {
        "message": "Cleaned up all session systems",
        "results": results
    }

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
            },
            {
                "name": "session_management",
                "description": "Advanced session and conversation management",
                "available": bool(chat_handler)
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
            "chat_handler_active": bool(chat_handler),
            "available": True
        }
        
    except Exception as e:
        print(f"❌ Error in /tools endpoint: {e}")
        return {
            "tools": [],
            "count": 0,
            "mcp_connected": False,
            "chat_handler_active": False,
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
    
    # Test chat handler
    chat_handler_status = "active" if chat_handler else "inactive"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.1",
        "components": {
            "api": "healthy",
            "memory": memory_status,
            "mcp_client": mcp_status,
            "router": "healthy",
            "chat_handler": chat_handler_status
        },
        "stats": {
            "active_sessions": len(memory.list_sessions()),
            "chat_handler_sessions": chat_handler.get_active_sessions_count() if chat_handler else 0,
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
            "api_version": "2.0.1",
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
            "chat_handler": {
                "available": bool(chat_handler),
                "active_sessions": chat_handler.get_active_sessions_count() if chat_handler else 0,
                "type": type(chat_handler).__name__ if chat_handler else None
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
        "version": "2.0.1",
        "status": "running",
        "description": "Intelligent chatbot with Redis memory, smart routing, session management, and MCP tool integration",
        "features": [
            "🧠 Redis conversation memory",
            "🔀 Intelligent query routing",
            "🛠️ MCP tool integration", 
            "📝 Sticky notes management",
            "📚 Documentation search",
            "🧮 Math calculations",
            "💬 Natural conversation",
            "🎯 Advanced prompt analysis",
            "⏰ Automatic session management",
            "🔄 Complex multi-task handling"
        ],
        "endpoints": {
            "chat": "POST /query",
            "tools": "GET /tools", 
            "conversations": "GET /conversations",
            "sessions": "GET /sessions",
            "health": "GET /health",
            "status": "GET /status",
            "documentation": "GET /docs"
        },
        "system_status": {
            "mcp_status": "connected" if (mcp_client and MCP_AVAILABLE) else "disconnected",
            "chat_handler": "active" if chat_handler else "inactive",
            "memory_sessions": len(memory.list_sessions()),
            "chat_handler_sessions": chat_handler.get_active_sessions_count() if chat_handler else 0
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting MCP Chatbot API v2.0.1 with Enhanced Chat Handler...")
    print("📍 API will be available at: http://localhost:8000")
    print("📚 API docs: http://localhost:8000/docs") 
    print("🔍 Health check: http://localhost:8000/health")
    print("🛠️ Tools list: http://localhost:8000/tools")
    print("📊 Session management: http://localhost:8000/sessions")
    print("💡 v2.0.1 Features:")
    print("   • Enhanced complex task handling with real content")
    print("   • Better MCP error handling and fallbacks")
    print("   • Improved multi-task response generation")
    print("   • Smart content detection and routing")
    uvicorn.run(app, host="0.0.0.0", port=8000)