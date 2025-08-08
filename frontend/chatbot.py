import streamlit as st
import httpx
from typing import Dict, Any
import json
import asyncio


class Chatbot:
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.current_tool_call = {"name": None, "args": None}
        # Initialize session state if not exists
        if "messages" not in st.session_state:
            st.session_state["messages"] = []
        self.messages = st.session_state["messages"]

    def display_message(self, message: Dict[str, Any]):
        """Display a message in the Streamlit chat interface"""
        
        if message["role"] == "user":
            with st.chat_message("user"):
                if isinstance(message["content"], str):
                    st.markdown(message["content"])
                elif isinstance(message["content"], list):
                    # Handle complex user content (like tool results)
                    for content in message["content"]:
                        if isinstance(content, dict):
                            if content.get("type") == "tool_result":
                                st.info(f"🔧 Tool Result from {content.get('name', 'unknown')}")
                                st.code(content.get("content", ""), language="json")
                        else:
                            st.markdown(str(content))

        elif message["role"] == "assistant":
            with st.chat_message("assistant"):
                # Show tool info if available
                if message.get("tool_used"):
                    st.info(f"🔧 Used tool: **{message['tool_used']}**")
                
                # Display main content
                if isinstance(message["content"], str):
                    st.markdown(message["content"])
                elif isinstance(message["content"], list):
                    # Handle complex assistant content
                    for content in message["content"]:
                        if isinstance(content, dict):
                            if content.get("type") == "text":
                                st.markdown(content["text"])
                            elif content.get("type") == "function_call":
                                st.info(f"🔧 Calling tool: **{content['name']}**")
                                if content.get("args"):
                                    st.json(content["args"])
                        else:
                            st.markdown(str(content))
                
                # Show status indicators
                if message.get("rate_limited"):
                    st.warning("🚫 Response was rate limited")
                elif message.get("fallback_used"):
                    st.info("ℹ️ Used fallback response")
                elif message.get("status") == "error":
                    st.error("❌ Response had errors")

    async def get_tools(self):
        """Fetch available tools from the API"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_url}/tools")
                if response.status_code == 200:
                    return response.json()
                else:
                    st.error(f"Failed to fetch tools: HTTP {response.status_code}")
                    return {"tools": []}
        except Exception as e:
            st.error(f"Error connecting to API: {str(e)}")
            return {"tools": []}

    async def check_health(self):
        """Check if the API is healthy"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_url}/health")
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def send_query(self, query: str):
        """Send a query to the API and return the response"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.api_url}/query",
                    json={
                        "query": query,
                        "session_id": st.session_state.get("session_id", None),
                        "use_routing": True
                    },
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    error_detail = f"HTTP {response.status_code}"
                    try:
                        error_data = response.json()
                        error_detail = error_data.get("detail", error_detail)
                    except:
                        pass
                    raise Exception(f"API Error: {error_detail}")
        except httpx.TimeoutException:
            raise Exception("Request timed out. The API might be processing a complex query.")
        except Exception as e:
            raise Exception(f"Failed to send query: {str(e)}")

    async def render(self):
        """Main render function for the Streamlit app"""
        st.title("🤖 MCP Chatbot Client")

        # Initialize session ID if not exists
        if "session_id" not in st.session_state:
            import uuid
            st.session_state["session_id"] = str(uuid.uuid4())

        # Sidebar with API status and tools
        with st.sidebar:
            st.subheader("🔧 Connection Status")
            
            # Check API health
            with st.spinner("Checking API status..."):
                health_status = await self.check_health()
                st.json(health_status)

            if health_status.get("status") == "healthy":
                st.success("✅ API Connected")
                
                # Show additional health info if available
                if "components" in health_status:
                    components = health_status["components"]
                    st.write("**Components:**")
                    for comp, status in components.items():
                        icon = "✅" if status in ("healthy", "connected") else "❌"
                        st.write(f"• {comp}: {icon}")
                        
            else:
                st.error("❌ API Disconnected")
                st.write(f"Error: {health_status.get('error', 'Unknown error')}")
                st.write(f"API URL: {self.api_url}")
                st.write("Make sure your FastAPI server is running!")
                return

            # Load and display tools
            st.subheader("🛠️ Available Tools")
            try:
                tools_result = await self.get_tools()
                tools = tools_result.get("tools", [])
                
                if tools:
                    for tool in tools:
                        with st.expander(f"🔧 {tool['name']}"):
                            st.write(tool.get('description', 'No description available'))
                            if tool.get('available'):
                                st.success("Available ✅")
                            else:
                                st.warning("Not available ⚠️")
                else:
                    st.write("No tools available")
                    
            except Exception as e:
                st.error(f"Failed to load tools: {str(e)}")

            # Session info
            st.subheader("📊 Session Info")
            st.write(f"Session: `{st.session_state['session_id'][:8]}...`")
            st.write(f"Messages: {len(st.session_state['messages'])}")

            # Clear chat button
            if st.button("🗑️ Clear Chat"):
                st.session_state["messages"] = []
                st.rerun()

        # Display existing messages
        for message in st.session_state["messages"]:
            self.display_message(message)

        # Chat input
        if query := st.chat_input("Enter your message here..."):
            # Add user message to session state
            user_message = {"role": "user", "content": query}
            st.session_state["messages"].append(user_message)
            
            # Display user message immediately
            self.display_message(user_message)
            
            # Send query to API
            with st.spinner("🤔 Thinking..."):
                try:
                    response_data = await self.send_query(query)
                    
                    # Debug info (only show in development)
                    if st.get_option("runner.magicEnabled"):
                        with st.expander("🔍 Debug: API Response", expanded=False):
                            st.json(response_data)
                    
                    # Handle both API response formats
                    if "messages" in response_data:
                        # New format: API returns full conversation history
                        api_messages = response_data["messages"]
                        st.session_state["messages"] = api_messages
                        
                        # Display only the latest assistant message
                        if api_messages and api_messages[-1]["role"] == "assistant":
                            self.display_message(api_messages[-1])
                            
                    else:
                        # Current format: API returns single response fields
                        response_content = (
                            response_data.get("response") or 
                            response_data.get("message") or 
                            response_data.get("content") or 
                            response_data.get("text") or
                            "No response received"
                        )
                        
                        assistant_message = {
                            "role": "assistant",
                            "content": response_content,
                            "tool_used": response_data.get("tool_used"),
                            "status": response_data.get("status", "success"),
                            "rate_limited": response_data.get("rate_limited", False),
                            "fallback_used": response_data.get("fallback_used", False),
                            "session_id": response_data.get("session_id")
                        }
                        
                        st.session_state["messages"].append(assistant_message)
                        self.display_message(assistant_message)
                        
                        # Update session ID if provided by API
                        if response_data.get("session_id"):
                            st.session_state["session_id"] = response_data["session_id"]
                        
                        # Show global status indicators
                        if response_data.get("rate_limited"):
                            st.warning("🚫 API is currently rate limited")
                        elif response_data.get("fallback_used"):
                            st.info("ℹ️ Using fallback response (limited functionality)")
                        elif response_data.get("status") == "error":
                            st.error(f"❌ API Error: {response_data.get('error', 'Unknown error')}")
                            
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    # Add error message to chat
                    error_message = {
                        "role": "assistant", 
                        "content": f"Sorry, I encountered an error: {str(e)}",
                        "status": "error"
                    }
                    st.session_state["messages"].append(error_message)
                    self.display_message(error_message)
            
            # Rerun to update the interface
            st.rerun()