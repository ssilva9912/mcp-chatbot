import asyncio
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
from datetime import datetime
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import traceback
import os
import json

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
from dotenv import load_dotenv

load_dotenv()

class MCPClient:
    def __init__(self, api_key: str = None, model_name: str = None):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # Use provided API key or get from environment
        api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        
        if not api_key:
            raise ValueError("API key required. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable")
        
        # Configure Gemini with updated model selection
        try:
            genai.configure(api_key=api_key)
            
            # Try different model names in order of preference
            model_options = [
                model_name,  # User specified model
                "gemini-2.0-flash-exp",  # Latest experimental
                "gemini-1.5-flash",      # Fast and reliable
                "gemini-1.5-pro",        # Original (might work)
                "gemini-pro",            # Fallback
            ]
            
            # Filter out None values
            model_options = [m for m in model_options if m is not None]
            
            self.model = None
            self.model_name = None
            
            for model_option in model_options:
                try:
                    print(f"🧪 Trying model: {model_option}")
                    self.model = genai.GenerativeModel(model_option)
                    
                    # Test the model with a simple request
                    test_response = self.model.generate_content("Hello")
                    
                    # If we get here, the model works
                    self.model_name = model_option
                    print(f"✅ Successfully using model: {model_option}")
                    break
                    
                except Exception as e:
                    print(f"❌ Model {model_option} failed: {str(e)[:100]}...")
                    continue
            
            if not self.model:
                raise ValueError("No working Gemini model found. Check your API key and model availability.")
                
        except Exception as e:
            print(f"❌ Failed to configure Gemini: {e}")
            raise
        
        self.tools = []
        self.gemini_tools = []

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server with timeout and better error handling"""
        try:
            # Check if server script exists
            if not os.path.exists(server_script_path):
                raise FileNotFoundError(f"Server script not found: {server_script_path}")
                
            is_python = server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")
            
            if not (is_python or is_js):
                raise ValueError("Server script must be a .py or .js file")

            print(f"🔌 Connecting to MCP server: {server_script_path}")
            
            command = "python" if is_python else "node"
            server_params = StdioServerParameters(
                command=command, 
                args=[server_script_path], 
                env=None
            )

            try:
                # Connection with 15 second timeout
                stdio_transport = await asyncio.wait_for(
                    self.exit_stack.enter_async_context(stdio_client(server_params)),
                    timeout=15.0
                )
                self.stdio, self.write = stdio_transport
                
                # Session creation with 10 second timeout
                self.session = await asyncio.wait_for(
                    self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write)),
                    timeout=10.0
                )

                # Initialize with 15 second timeout
                await asyncio.wait_for(self.session.initialize(), timeout=15.0)

                # List available tools with 10 second timeout
                response = await asyncio.wait_for(self.session.list_tools(), timeout=10.0)
                self.tools = response.tools if hasattr(response, 'tools') else []
                
                # Convert to Gemini format with better error handling
                self.gemini_tools = self._convert_tools_to_gemini_format(self.tools)
                
                tool_names = [tool.name for tool in self.tools] if self.tools else []
                print(f"✅ Connected to MCP server with tools: {tool_names}")
                print(f"🤖 Using Gemini model: {self.model_name}")
                
                return True
                
            except asyncio.TimeoutError:
                print(f"⏰ Connection timeout after 15 seconds for {server_script_path}")
                raise TimeoutError(f"MCP server connection timed out: {server_script_path}")
                
        except Exception as e:
            print(f"❌ Failed to connect to MCP server: {e}")
            print(f"📝 Traceback: {traceback.format_exc()}")
            raise

    def _convert_tools_to_gemini_format(self, mcp_tools) -> List[Tool]:
        """Convert MCP tools to Gemini function calling format with better error handling"""
        if not mcp_tools:
            print("⚠️ No MCP tools to convert")
            return []
            
        gemini_functions = []
        
        try:
            for tool in mcp_tools:
                print(f"🔧 Converting tool: {tool.name}")
                
                # Convert MCP tool schema to Gemini format
                parameters = {}
                required = []
                
                # Handle inputSchema properly
                input_schema = getattr(tool, 'inputSchema', {})
                if isinstance(input_schema, dict):
                    properties = input_schema.get('properties', {})
                    required = input_schema.get('required', [])
                    
                    for prop_name, prop_schema in properties.items():
                        if isinstance(prop_schema, dict):
                            param_type = self._convert_json_type_to_gemini(prop_schema.get('type', 'string'))
                            parameters[prop_name] = {
                                'type_': param_type,
                                'description': prop_schema.get('description', f'Parameter {prop_name}')
                            }

                function_decl = FunctionDeclaration(
                    name=tool.name,
                    description=getattr(tool, 'description', f"Tool {tool.name}"),
                    parameters={
                        'type_': 'OBJECT',
                        'properties': parameters,
                        'required': required
                    }
                )
                gemini_functions.append(function_decl)
                print(f"   ✅ Successfully converted tool: {tool.name}")
                
            if gemini_functions:
                print(f"✅ Successfully converted {len(gemini_functions)} tools to Gemini format")
                return [Tool(function_declarations=gemini_functions)]
            else:
                print("⚠️ No functions converted to Gemini format")
                return []
            
        except Exception as e:
            print(f"⚠️ Error converting tools to Gemini format: {e}")
            print(f"📝 Traceback: {traceback.format_exc()}")
            return []

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
        return type_mapping.get(json_type.lower(), 'STRING')

    # NEW METHOD: Direct Gemini access without tools
    async def process_query_direct(self, query: str) -> str:
        """Process a query using Gemini directly WITHOUT tools for general conversation"""
        try:
            print(f"🎯 Processing direct query: {query[:100]}...")
            print(f"🤖 Using model: {self.model_name} (no tools)")
            
            # Use Gemini directly without tools
            response = self.model.generate_content(query)
            
            if response and response.text:
                result = response.text.strip()
                print(f"✅ Generated direct response ({len(result)} chars) using {self.model_name}")
                return result
            else:
                return "I'm not sure how to help with that. Could you try rephrasing your question?"
                
        except Exception as e:
            error_msg = f"❌ Error processing direct query with {self.model_name}: {str(e)}"
            print(error_msg)
            print(f"📝 Traceback: {traceback.format_exc()}")
            return f"I encountered an error: {str(e)}. Please try again."

    async def process_query(self, query: str) -> str:
        """Process a query using Gemini and available tools with better debugging"""
        try:
            print(f"🎯 Processing query: {query[:100]}...")
            print(f"🤖 Using model: {self.model_name}")
            
            # Start chat with Gemini
            chat = self.model.start_chat()
            
            # Send initial message with tools if available
            if self.gemini_tools:
                try:
                    print(f"🔧 Sending message with {len(self.gemini_tools)} tool groups")
                    response = chat.send_message(query, tools=self.gemini_tools)
                    print("✅ Sent message with tools")
                except Exception as e:
                    print(f"⚠️ Tool format issue, trying without tools: {e}")
                    response = chat.send_message(query)
            else:
                print("📝 No tools available, sending direct message")
                response = chat.send_message(query)
            
            final_text = []
            
            # Process the response with better debugging
            if response.candidates and response.candidates[0].content.parts:
                print(f"📥 Processing {len(response.candidates[0].content.parts)} response parts")
                
                for i, part in enumerate(response.candidates[0].content.parts):
                    print(f"   Part {i+1}: {type(part)}")
                    
                    if hasattr(part, 'text') and part.text:
                        print(f"     Text content: {part.text[:100]}...")
                        final_text.append(part.text)
                        
                    elif hasattr(part, 'function_call') and part.function_call:
                        # Handle function call
                        function_call = part.function_call
                        tool_name = function_call.name
                        tool_args = dict(function_call.args) if function_call.args else {}
                        
                        print(f"🔧 Executing tool: {tool_name} with args: {tool_args}")
                        
                        try:
                            # Execute tool via MCP with timeout
                            result = await asyncio.wait_for(
                                self.session.call_tool(tool_name, tool_args),
                                timeout=30.0  # 30 second timeout for tool execution
                            )
                            
                            # Extract content from result
                            result_content = ""
                            if hasattr(result, 'content'):
                                if isinstance(result.content, list):
                                    # Handle list of TextContent objects
                                    for content_item in result.content:
                                        if hasattr(content_item, 'text'):
                                            result_content += content_item.text + "\n"
                                        else:
                                            result_content += str(content_item) + "\n"
                                else:
                                    result_content = str(result.content)
                            else:
                                result_content = str(result)
                            
                            result_content = result_content.strip()
                            print(f"🔧 Extracted result content: {result_content[:200]}...")
                            
                            # Save tool result for debugging
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            os.makedirs("tool_results", exist_ok=True)
                            with open(f"tool_results/result_{timestamp}.txt", "w", encoding="utf-8") as f:
                                f.write(f"Model: {self.model_name}\nTool: {tool_name}\nArgs: {json.dumps(tool_args, indent=2)}\nRaw Result: {str(result)}\nExtracted Content: {result_content}")
                            
                            # Send tool result back to Gemini
                            function_response_part = genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"result": result_content}
                                )
                            )
                            
                            # Get follow-up response from Gemini
                            print("🔄 Sending tool result back to Gemini...")
                            followup_response = chat.send_message([function_response_part])
                            
                            # Process follow-up response
                            if followup_response.candidates and followup_response.candidates[0].content.parts:
                                for followup_part in followup_response.candidates[0].content.parts:
                                    if hasattr(followup_part, 'text') and followup_part.text:
                                        final_text.append(followup_part.text)
                                        print(f"📥 Added followup text: {followup_part.text[:100]}...")
                                        
                        except asyncio.TimeoutError:
                            error_msg = f"⏰ Tool {tool_name} timed out after 30 seconds"
                            print(error_msg)
                            final_text.append(error_msg)
                        except Exception as e:
                            error_msg = f"❌ Error executing tool {tool_name}: {str(e)}"
                            print(error_msg)
                            print(f"📝 Traceback: {traceback.format_exc()}")
                            final_text.append(error_msg)
            else:
                print("⚠️ No response parts found")
            
            result = "\n".join(final_text) if final_text else "No response generated."
            print(f"✅ Generated response ({len(result)} chars) using {self.model_name}")
            return result
            
        except Exception as e:
            error_msg = f"❌ Error processing query with {self.model_name}: {str(e)}"
            print(error_msg)
            print(f"📝 Traceback: {traceback.format_exc()}")
            return f"I encountered an error with model {self.model_name}: {str(e)}. Please try again."

    async def list_tools(self) -> List[Dict]:
        """Return list of available tools"""
        try:
            if not self.tools:
                return []
                
            return [
                {
                    "name": tool.name,
                    "description": getattr(tool, 'description', f"Tool {tool.name}"),
                    "available": True,
                    "model": self.model_name
                }
                for tool in self.tools
            ]
        except Exception as e:
            print(f"❌ Error listing tools: {e}")
            return []

    async def call_tool(self, tool_name: str, tool_args: Dict) -> Dict:
        """Call a specific tool directly"""
        try:
            if not self.session:
                raise Exception("Not connected to MCP server")
                
            print(f"🔧 Direct tool call: {tool_name} with args: {tool_args}")
            print(f"🤖 Using model: {self.model_name}")
            
            # Add timeout to direct tool calls too
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, tool_args),
                timeout=30.0
            )
            
            # Extract content properly
            result_content = ""
            if hasattr(result, 'content'):
                if isinstance(result.content, list):
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            result_content += content_item.text + "\n"
                        else:
                            result_content += str(content_item) + "\n"
                else:
                    result_content = str(result.content)
            else:
                result_content = str(result)
            
            return {
                "response": result_content.strip(), 
                "success": True,
                "model": self.model_name
            }
            
        except asyncio.TimeoutError:
            return {
                "response": f"Tool {tool_name} timed out after 30 seconds", 
                "success": False,
                "model": self.model_name
            }
        except Exception as e:
            print(f"❌ Direct tool call error: {e}")
            print(f"📝 Traceback: {traceback.format_exc()}")
            return {
                "response": f"Tool execution failed: {str(e)}", 
                "success": False,
                "model": self.model_name
            }

    async def cleanup(self):
        """Clean up resources"""
        try:
            print(f"🧹 Cleaning up MCP client (model: {self.model_name})...")
            await self.exit_stack.aclose()
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

# For testing with different models
async def test_models():
    """Test different Gemini models"""
    models_to_test = [
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash", 
        "gemini-1.5-pro",
        "gemini-pro"
    ]
    
    for model in models_to_test:
        try:
            print(f"\n🧪 Testing model: {model}")
            client = MCPClient(model_name=model)
            print(f"✅ {model} works!")
            await client.cleanup()
            break
        except Exception as e:
            print(f"❌ {model} failed: {str(e)[:100]}...")
            continue

# For testing
async def main():
    """Test the MCP client with updated models"""
    try:
        client = MCPClient()  # Will auto-select working model
        
        # Test connection
        server_paths = ["../server/server.py", "./server.py", "../server.py"]
        
        connected = False
        for path in server_paths:
            if os.path.exists(path):
                try:
                    print(f"🔌 Trying to connect to: {path}")
                    await client.connect_to_server(path)
                    connected = True
                    break
                except Exception as e:
                    print(f"⚠️ Failed to connect to {path}: {e}")
                    continue
        
        if not connected:
            print("❌ No server connection successful")
            return
            
        # Test both types of queries
        print("\n🧪 Testing tool query...")
        response1 = await client.process_query("Add a note saying 'Model test successful'")
        print(f"📥 Tool Response: {response1}")
        
        print("\n🧪 Testing direct query...")
        response2 = await client.process_query_direct("How can I make a Caesar salad?")
        print(f"📥 Direct Response: {response2}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        print(f"📝 Traceback: {traceback.format_exc()}")
    finally:
        if 'client' in locals():
            await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())