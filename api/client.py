from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
import traceback
from utils.logger import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
import json
import os

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool, content_types


class MCPClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is required for Gemini integration")
        
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # Configure Gemini
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        except Exception as e:
            logger.error(f"Failed to configure Gemini: {str(e)}")
            raise ValueError(f"Invalid API key or Gemini configuration failed: {str(e)}")
        
        self.tools = []
        self.gemini_tools = []
        self.messages = []
        self.logger = logger

    async def call_tool(self, tool_name: str, tool_args: dict):
        """Call a tool with the given name and arguments"""
        try:
            result = await self.session.call_tool(tool_name, tool_args)
            return result
        except Exception as e:
            self.logger.error(f"Failed to call tool: {str(e)}")
            raise Exception(f"Failed to call tool: {str(e)}")

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server with better error handling"""
        try:
            # Check if server script exists
            if not os.path.exists(server_script_path):
                raise FileNotFoundError(f"Server script not found: {server_script_path}")
            
            is_python = server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")
            if not (is_python or is_js):
                raise ValueError("Server script must be a .py or .js file")

            self.logger.info(f"Attempting to connect to server using script: {server_script_path}")
            
            command = "python" if is_python else "node"
            server_params = StdioServerParameters(
                command=command, 
                args=[server_script_path], 
                env=None
            )

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(self.stdio, self.write)
            )

            await self.session.initialize()
            mcp_tools = await self.get_mcp_tools()
            
            # Convert MCP tools to both internal format and Gemini format
            self.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in mcp_tools
            ]
            
            # Convert to Gemini tool format
            self.gemini_tools = self._convert_to_gemini_tools(mcp_tools)
            
            self.logger.info(
                f"Successfully connected to server. Available tools: {[tool['name'] for tool in self.tools]}"
            )
            return True
            
        except FileNotFoundError as e:
            self.logger.error(f"Server script file error: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to connect to server: {str(e)}")
            self.logger.debug(f"Connection error details: {traceback.format_exc()}")
            raise Exception(f"Failed to connect to server: {str(e)}")

    def _convert_to_gemini_tools(self, mcp_tools) -> List[Tool]:
        """Convert MCP tools to Gemini tool format"""
        gemini_functions = []
        
        for tool in mcp_tools:
            # Convert JSON Schema to Gemini parameter format
            parameters = {}
            required = []
            
            if hasattr(tool.inputSchema, 'properties') and tool.inputSchema.properties:
                for prop_name, prop_schema in tool.inputSchema.properties.items():
                    param_type = self._convert_json_type_to_gemini(prop_schema.get('type', 'string'))
                    parameters[prop_name] = {
                        'type_': param_type,
                        'description': prop_schema.get('description', '')
                    }
                    
                if hasattr(tool.inputSchema, 'required') and tool.inputSchema.required:
                    required = tool.inputSchema.required
            
            function_decl = FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters={
                    'type_': 'OBJECT',
                    'properties': parameters,
                    'required': required
                }
            )
            gemini_functions.append(function_decl)
        
        return [Tool(function_declarations=gemini_functions)] if gemini_functions else []

    def _convert_json_type_to_gemini(self, json_type: str) -> str:
        """Convert JSON Schema types to Gemini types"""
        type_mapping = {
            'string': 'STRING',
            'integer': 'INTEGER',
            'number': 'NUMBER',
            'boolean': 'BOOLEAN',
            'array': 'ARRAY',
            'object': 'OBJECT'
        }
        return type_mapping.get(json_type, 'STRING')

    async def get_mcp_tools(self):
        try:
            self.logger.info("Requesting MCP tools from the server.")
            response = await self.session.list_tools()
            tools = response.tools
            return tools
        except Exception as e:
            self.logger.error(f"Failed to get MCP tools: {str(e)}")
            self.logger.debug(f"Error details: {traceback.format_exc()}")
            raise Exception(f"Failed to get tools: {str(e)}")

    def _convert_messages_to_gemini_format(self, messages: List[Dict]) -> List[content_types.ContentDict]:
        """Convert internal message format to Gemini format"""
        gemini_messages = []
        
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            
            if isinstance(msg["content"], str):
                gemini_messages.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            elif isinstance(msg["content"], list):
                parts = []
                for content_item in msg["content"]:
                    if isinstance(content_item, dict):
                        if content_item.get("type") == "text":
                            parts.append({"text": content_item["text"]})
                        elif content_item.get("type") == "tool_result":
                            # Convert tool results to text for Gemini
                            result_text = f"Tool result: {content_item.get('content', '')}"
                            parts.append({"text": result_text})
                    else:
                        parts.append({"text": str(content_item)})
                
                if parts:
                    gemini_messages.append({
                        "role": role,
                        "parts": parts
                    })
        
        return gemini_messages

    async def call_llm(self) -> Any:
        """Call Gemini with the current messages and better error handling"""
        try:
            if not self.messages:
                raise ValueError("No messages to process")
                
            # Convert messages to Gemini format
            gemini_messages = self._convert_messages_to_gemini_format(self.messages)
            
            if not gemini_messages:
                raise ValueError("Failed to convert messages to Gemini format")
            
            # Create chat session
            chat = self.model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
            
            # Get the last message (current user input)
            last_message = gemini_messages[-1]["parts"][0]["text"] if gemini_messages else ""
            
            if not last_message:
                raise ValueError("No message content to send to Gemini")
            
            # Send message with tools if available
            if self.gemini_tools:
                self.logger.debug(f"Sending message with {len(self.gemini_tools)} tools available")
                response = chat.send_message(last_message, tools=self.gemini_tools)
            else:
                self.logger.debug("Sending message without tools")
                response = chat.send_message(last_message)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Failed to call Gemini: {str(e)}")
            self.logger.debug(f"Gemini error details: {traceback.format_exc()}")
            raise Exception(f"Failed to call Gemini: {str(e)}")

    async def process_query(self, query: str):
        """Process a query using Gemini and available tools"""
        try:
            self.logger.info(f"Processing new query: {query[:100]}...")

            # Add the initial user message
            user_message = {"role": "user", "content": query}
            self.messages.append(user_message)
            await self.log_conversation(self.messages)
            messages = [user_message]

            while True:
                self.logger.debug("Calling Gemini API")
                response = await self.call_llm()

                # Check if response has function calls
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    
                    if hasattr(candidate.content, 'parts'):
                        has_function_calls = any(
                            hasattr(part, 'function_call') and part.function_call 
                            for part in candidate.content.parts
                        )
                        
                        if not has_function_calls:
                            # Simple text response
                            text_parts = [
                                part.text for part in candidate.content.parts 
                                if hasattr(part, 'text')
                            ]
                            full_text = '\n'.join(text_parts)
                            
                            assistant_message = {"role": "assistant", "content": full_text}
                            self.messages.append(assistant_message)
                            await self.log_conversation(self.messages)
                            messages.append(assistant_message)
                            break
                        else:
                            # Response with function calls
                            assistant_content = []
                            
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    assistant_content.append({"type": "text", "text": part.text})
                                elif hasattr(part, 'function_call') and part.function_call:
                                    # Execute the function call
                                    func_call = part.function_call
                                    tool_name = func_call.name
                                    tool_args = dict(func_call.args) if func_call.args else {}
                                    
                                    self.logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                                    
                                    try:
                                        result = await self.session.call_tool(tool_name, tool_args)
                                        self.logger.info(f"Tool result: {result}")
                                        
                                        # Add function call to assistant message
                                        assistant_content.append({
                                            "type": "function_call",
                                            "name": tool_name,
                                            "args": tool_args
                                        })
                                        
                                        # Add tool result as user message
                                        tool_result_message = {
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "tool_result",
                                                    "name": tool_name,
                                                    "content": str(result.content),
                                                }
                                            ],
                                        }
                                        
                                        # Add assistant message with function call
                                        assistant_message = {"role": "assistant", "content": assistant_content}
                                        self.messages.append(assistant_message)
                                        messages.append(assistant_message)
                                        
                                        # Add tool result
                                        self.messages.append(tool_result_message)
                                        await self.log_conversation(self.messages)
                                        messages.append(tool_result_message)
                                        
                                    except Exception as e:
                                        error_msg = f"Tool execution failed: {str(e)}"
                                        self.logger.error(error_msg)
                                        raise Exception(error_msg)
                    else:
                        # Fallback for unexpected response format
                        assistant_message = {"role": "assistant", "content": str(response)}
                        self.messages.append(assistant_message)
                        await self.log_conversation(self.messages)
                        messages.append(assistant_message)
                        break
                else:
                    # Fallback for unexpected response format
                    assistant_message = {"role": "assistant", "content": str(response)}
                    self.messages.append(assistant_message)
                    await self.log_conversation(self.messages)
                    messages.append(assistant_message)
                    break

            return messages

        except Exception as e:
            self.logger.error(f"Error processing query: {str(e)}")
            self.logger.debug(f"Query processing error details: {traceback.format_exc()}")
            raise

    async def log_conversation(self, conversation: list):
        """Log the conversation to json file"""
        # Create conversations directory if it doesn't exist
        os.makedirs("conversations", exist_ok=True)

        # Convert conversation to JSON-serializable format
        serializable_conversation = []
        for message in conversation:
            try:
                serializable_message = {
                    "role": message["role"],
                    "content": message["content"]
                }
                serializable_conversation.append(serializable_message)
            except Exception as e:
                self.logger.error(f"Error processing message: {str(e)}")
                self.logger.debug(f"Message content: {message}")
                raise

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join("conversations", f"conversation_{timestamp}.json")
        
        try:
            with open(filepath, "w") as f:
                json.dump(serializable_conversation, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error writing conversation to file: {str(e)}")
            self.logger.debug(f"Serializable conversation: {serializable_conversation}")
            raise

    async def cleanup(self):
        """Clean up resources"""
        try:
            self.logger.info("Cleaning up resources")
            await self.exit_stack.aclose()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")