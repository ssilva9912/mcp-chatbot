#!/usr/bin/env python3
"""
Complete MCP Server with documentation search, notes, math tools, and general chat
"""

import asyncio
import json
import sys
import re
import operator
import os
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
from mcp.types import (
    CallToolRequest,
    ListToolsRequest,
    Tool,
    TextContent,
)

# Load environment variables
load_dotenv(dotenv_path="C:/Users/Sebastian/Documents/Datasets/Langgraph_Projects/mcp-client/api/.env")

# Simple in-memory notes storage
notes_storage = []

# Constants for documentation search
USER_AGENT = "docs-app/1.0"
SERPER_URL = "https://google.serper.dev/search"

# Docs site mapping
docs_urls = {
    "langchain": "python.langchain.com/docs",
    "llama-index": "docs.llamaindex.ai/en/stable",
    "openai": "platform.openai.com/docs",
    "anthropic": "docs.anthropic.com",
    "huggingface": "huggingface.co/docs",
    "pytorch": "pytorch.org/docs",
    "tensorflow": "tensorflow.org/api_docs",
}

server = Server("mcp-chatbot-server")

# Web search using Serper
async def search_web(query: str) -> dict:
    """Search the web using Serper API"""
    payload = json.dumps({"q": query, "num": 3})
    serper_api_key = os.getenv("SERPER_API_KEY")
    
    if not serper_api_key:
        return {"organic": [], "error": "SERPER_API_KEY not found in environment variables"}
    
    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(SERPER_URL, headers=headers, data=payload, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {"organic": [], "error": "Search timeout"}
        except Exception as e:
            return {"organic": [], "error": str(e)}

# Fetch plain text from a URL
async def fetch_url(url: str) -> str:
    """Fetch and extract text content from a URL with proper encoding handling"""
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            
            # Get the response content with proper encoding
            response.encoding = response.charset_encoding or 'utf-8'
            html_content = response.text
            
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            # Get text and clean it up
            text = soup.get_text()
            
            # Clean up the text with better Unicode handling
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Handle problematic characters for Windows
            try:
                # Try to encode/decode to handle Windows encoding issues
                text = text.encode('utf-8', errors='ignore').decode('utf-8')
                
                # Replace common problematic characters
                replacements = {
                    '\u2018': "'",  # Left single quotation mark
                    '\u2019': "'",  # Right single quotation mark
                    '\u201c': '"',  # Left double quotation mark
                    '\u201d': '"',  # Right double quotation mark
                    '\u2013': '-',  # En dash
                    '\u2014': '--', # Em dash
                    '\u2026': '...', # Horizontal ellipsis
                    '\u00a0': ' ',  # Non-breaking space
                }
                
                for old_char, new_char in replacements.items():
                    text = text.replace(old_char, new_char)
                
                # Remove any remaining non-ASCII characters that might cause issues
                text = ''.join(char if ord(char) < 128 or char.isspace() else '?' for char in text)
                
            except Exception as encoding_error:
                print(f"Encoding error: {encoding_error}")
                # Fallback: remove all non-ASCII characters
                text = ''.join(char for char in text if ord(char) < 128)
            
            return text
            
        except httpx.TimeoutException:
            return "Timeout while fetching URL"
        except UnicodeEncodeError as e:
            return f"Encoding error while processing URL content: {str(e)}"
        except Exception as e:
            return f"Error fetching URL: {str(e)}"

def safe_eval_math(expression: str) -> float:
    """Safely evaluate mathematical expressions"""
    # Remove whitespace
    expression = expression.replace(" ", "")
    
    # Only allow numbers, operators, parentheses, and decimal points
    if not re.match(r'^[\d+\-*/().]+$', expression):
        raise ValueError("Invalid characters in expression")
    
    try:
        # Use eval with restricted globals for basic math
        allowed_names = {
            "__builtins__": {},
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
        }
        result = eval(expression, allowed_names)
        return float(result)
    except ZeroDivisionError:
        raise ValueError("Division by zero")
    except Exception as e:
        raise ValueError(f"Invalid expression: {str(e)}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools with proper schema format"""
    return [
        Tool(
            name="general_chat",
            description="Handle general conversations, questions, and provide information on various topics",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's question or conversation input"
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="add_note",
            description="Add a simple note to memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string", 
                        "description": "The note content to save"
                    }
                },
                "required": ["message"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="read_notes", 
            description="Read all saved notes",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        ),
        Tool(
            name="search_notes",
            description="Search notes for specific content",
            inputSchema={
                "type": "object", 
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term to find in notes"
                    }
                },
                "required": ["query"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="simple_math",
            description="Perform safe mathematical calculations", 
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string", 
                        "description": "Mathematical expression (e.g., '2 + 3 * 4')"
                    }
                },
                "required": ["expression"],
                "additionalProperties": False
            }
        ),
        Tool(
            name="get_docs",
            description="Search documentation for a given query and library (langchain, openai, llama-index, anthropic, huggingface, pytorch, tensorflow)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search for (e.g., 'Chroma DB integration')"
                    },
                    "library": {
                        "type": "string",
                        "description": "The library to search in (langchain, openai, llama-index, anthropic, huggingface, pytorch, tensorflow)"
                    }
                },
                "required": ["query", "library"],
                "additionalProperties": False
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls with proper error handling and formatting"""
    
    try:
        if name == "general_chat":
            query = arguments.get("query", "").strip()
            if not query:
                return [TextContent(
                    type="text", 
                    text="ERROR: Query cannot be empty"
                )]
            
            try:
                # Option 1: Call external LLM (implement based on your needs)
                # response = await call_external_llm(query)
                # return [TextContent(type="text", text=response)]
                
                # Option 2: Use local Ollama (implement based on your setup)
                # response = await call_ollama(query)
                # return [TextContent(type="text", text=response)]
                
                # Option 3: Basic conversational responses for now
                query_lower = query.lower()
                
                # Handle greetings
                if any(greeting in query_lower for greeting in ["hello", "hi", "hey", "good morning", "good afternoon"]):
                    return [TextContent(
                        type="text",
                        text="Hello! I'm here to help with conversations, answer questions, manage your notes, perform calculations, and search documentation. What can I do for you today?"
                    )]
                
                # Handle farewells
                elif any(farewell in query_lower for farewell in ["bye", "goodbye", "see you", "thanks", "thank you"]):
                    return [TextContent(
                        type="text",
                        text="You're welcome! Feel free to ask if you need help with notes, calculations, or documentation searches. Have a great day!"
                    )]
                
                # For all other queries, indicate need for LLM integration
                else:
                    return [TextContent(
                        type="text",
                        text=f"I'd like to help you with '{query}', but I need to be connected to a conversational AI service to handle general questions. For now, I can help you with:\n\n• Managing notes (add_note, read_notes, search_notes)\n• Mathematical calculations (simple_math)\n• Searching documentation (get_docs)\n\nWould you like to use any of these tools instead?"
                    )]
                    
            except Exception as e:
                return [TextContent(
                    type="text", 
                    text=f"Error handling conversation: {str(e)}"
                )]

        elif name == "add_note":
            message = arguments.get("message", "").strip()
            if not message:
                return [TextContent(
                    type="text", 
                    text="ERROR: Note message cannot be empty"
                )]
            
            note_id = len(notes_storage) + 1
            note = {
                "id": note_id, 
                "content": message,
                "timestamp": asyncio.get_event_loop().time()
            }
            notes_storage.append(note)
            
            return [TextContent(
                type="text", 
                text=f"Successfully saved note #{note_id}: '{message}'"
            )]
        
        elif name == "read_notes":
            if not notes_storage:
                return [TextContent(
                    type="text", 
                    text="No notes found. Use 'add_note' to create your first note!"
                )]
            
            notes_list = []
            for note in notes_storage:
                notes_list.append(f"#{note['id']}: {note['content']}")
            
            notes_text = "\n".join(notes_list)
            return [TextContent(
                type="text", 
                text=f"Your saved notes ({len(notes_storage)} total):\n\n{notes_text}"
            )]
        
        elif name == "search_notes":
            query = arguments.get("query", "").strip().lower()
            if not query:
                return [TextContent(
                    type="text", 
                    text="ERROR: Search query cannot be empty"
                )]
            
            if not notes_storage:
                return [TextContent(
                    type="text", 
                    text="No notes to search. Add some notes first!"
                )]
            
            matching_notes = []
            for note in notes_storage:
                if query in note['content'].lower():
                    matching_notes.append(f"#{note['id']}: {note['content']}")
            
            if matching_notes:
                results_text = "\n".join(matching_notes)
                return [TextContent(
                    type="text", 
                    text=f"Found {len(matching_notes)} notes matching '{query}':\n\n{results_text}"
                )]
            else:
                return [TextContent(
                    type="text", 
                    text=f"No notes found matching '{query}'. Try a different search term."
                )]
        
        elif name == "simple_math":
            expression = arguments.get("expression", "").strip()
            if not expression:
                return [TextContent(
                    type="text", 
                    text="ERROR: Mathematical expression cannot be empty"
                )]
            
            try:
                result = safe_eval_math(expression)
                
                # Format result nicely
                if result == int(result):
                    formatted_result = str(int(result))
                else:
                    formatted_result = f"{result:.6f}".rstrip('0').rstrip('.')
                
                return [TextContent(
                    type="text", 
                    text=f"{expression} = {formatted_result}"
                )]
                
            except ValueError as e:
                return [TextContent(
                    type="text", 
                    text=f"Math error: {str(e)}"
                )]
            except Exception as e:
                return [TextContent(
                    type="text", 
                    text=f"Calculation failed: {str(e)}"
                )]
        
        elif name == "get_docs":
            query = arguments.get("query", "").strip()
            library = arguments.get("library", "").strip().lower()
            
            if not query:
                return [TextContent(
                    type="text", 
                    text="ERROR: Documentation query cannot be empty"
                )]
            
            if not library:
                return [TextContent(
                    type="text", 
                    text="ERROR: Library parameter cannot be empty"
                )]
            
            if library not in docs_urls:
                available_libs = ', '.join(docs_urls.keys())
                return [TextContent(
                    type="text", 
                    text=f"ERROR: Library '{library}' not supported. Choose from: {available_libs}"
                )]
            
            try:
                # Search for documentation
                search_query = f"site:{docs_urls[library]} {query}"
                print(f"Searching docs: {search_query}")
                
                results = await search_web(search_query)
                
                if "error" in results:
                    return [TextContent(
                        type="text", 
                        text=f"Search error: {results['error']}"
                    )]
                
                if not results.get("organic"):
                    return [TextContent(
                        type="text", 
                        text=f"No documentation results found for '{query}' in {library} docs. Try a different search term or library."
                    )]
                
                # Fetch content from the top results
                combined_text = f"Documentation search results for '{query}' in {library}:\n\n"
                
                for i, result in enumerate(results["organic"][:2], 1):  # Limit to top 2 results
                    title = result.get("title", "Unknown")
                    url = result.get("link", "")
                    
                    combined_text += f"=== Result {i}: {title} ===\n"
                    combined_text += f"URL: {url}\n\n"
                    
                    # Fetch the actual content
                    content = await fetch_url(url)
                    
                    # Limit content length
                    if len(content) > 3000:
                        content = content[:3000] + "...\n[Content truncated for length]"
                    
                    combined_text += content + "\n\n"
                
                # Limit total response size
                if len(combined_text) > 8000:
                    combined_text = combined_text[:8000] + "...\n[Response truncated for length]"
                
                return [TextContent(
                    type="text", 
                    text=combined_text
                )]
                
            except Exception as e:
                return [TextContent(
                    type="text", 
                    text=f"Documentation search failed: {str(e)}"
                )]
        
        else:
            return [TextContent(
                type="text", 
                text=f"Unknown tool: '{name}'. Available tools: general_chat, add_note, read_notes, search_notes, simple_math, get_docs"
            )]
    
    except Exception as e:
        # Catch any unexpected errors
        return [TextContent(
            type="text", 
            text=f"Server error processing '{name}': {str(e)}"
        )]

async def main():
    """Run the server with proper error handling"""
    try:
        print("Starting MCP Chatbot Server...")
        print("Available tools:")
        print("  * general_chat: Handle general conversations and questions")
        print("  * add_note: Save a note to memory")
        print("  * read_notes: Display all saved notes")
        print("  * search_notes: Search through your notes")
        print("  * simple_math: Perform mathematical calculations")
        print("  * get_docs: Search documentation (langchain, openai, llama-index, etc.)")
        print("Server ready for connections...")
        
        # Check if SERPER_API_KEY is available
        if os.getenv("SERPER_API_KEY"):
            print("SERPER_API_KEY found - documentation search enabled")
        else:
            print("WARNING: SERPER_API_KEY not found - documentation search will be limited")
        
        # Set environment encoding for Windows
        if os.name == 'nt':  # Windows
            import locale
            try:
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            except:
                try:
                    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
                except:
                    print("Note: Using default locale for text encoding")
        
        # Use stdio transport
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream, 
                InitializationOptions(
                    server_name="mcp-chatbot-server",
                    server_version="1.2.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server error: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)