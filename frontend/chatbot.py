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
                    json={"query": query},
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

        # Sidebar with API status and tools
        with st.sidebar:
            st.subheader("🔧 Connection Status")
            
            # Check API health
            with st.spinner("Checking API status..."):
                health_status = await self.check_health()
            
            if health_status.get("status") == "healthy":
                st.success("✅ API Connected")
                st.write(f"Tools available: {health_status.get('tools_available', 'Unknown')}")
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
                else:
                    st.write("No tools available")
                    
            except Exception as e:
                st.error(f"Failed to load tools: {str(e)}")

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
                    
                    if "messages" in response_data:
                        # Replace the entire message history with the API response
                        # (skip the first message as it's the user message we just added)
                        api_messages = response_data["messages"]
                        if len(api_messages) > 1:
                            # Add only the new messages (assistant responses and tool results)
                            new_messages = api_messages[1:]  # Skip the user message
                            st.session_state["messages"].extend(new_messages)
                            
                            # Display new messages
                            for message in new_messages:
                                self.display_message(message)
                    else:
                        st.error("Unexpected response format from API")
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    # Add error message to chat
                    error_message = {"role": "assistant", "content": f"Sorry, I encountered an error: {str(e)}"}
                    st.session_state["messages"].append(error_message)
                    self.display_message(error_message)
            
            # Rerun to update the interface
            st.rerun()