from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import httpx
import json
import os
from bs4 import BeautifulSoup

# Load .env file (set the full path if needed)
load_dotenv(dotenv_path="C:/Users/Sebastian/Documents/Datasets/Langgraph_Projects/mcp-client/api/.env")

# Initialize the MCP tool host
mcp = FastMCP("docs")

# Constants
USER_AGENT = "docs-app/1.0"
SERPER_URL = "https://google.serper.dev/search"

# Docs site mapping
docs_urls = {
    "langchain": "python.langchain.com/docs",
    "llama-index": "docs.llamaindex.ai/en/stable",
    "openai": "platform.openai.com/docs",
}

# Web search using Serper
async def search_web(query: str) -> dict:
    payload = json.dumps({"q": query, "num": 2})
    serper_api_key = os.getenv("SERPER_API_KEY")

    if not serper_api_key:
        raise ValueError("SERPER_API_KEY not found in environment variables")

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
            return {"organic": []}
        except Exception as e:
            return {"organic": [], "error": str(e)}

# Fetch plain text from a URL
async def fetch_url(url: str) -> str:
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        try:
            response = await client.get(url, timeout=30.0)
            soup = BeautifulSoup(response.text, "html.parser")
            return soup.get_text()
        except httpx.TimeoutException:
            return "Timeout while fetching URL"
        except Exception as e:
            return f"Error fetching URL: {str(e)}"

# Tool registration
@mcp.tool()
async def get_docs(query: str, library: str) -> str:
    """
    Search the latest docs for a given query and library.
    Supports langchain, openai, and llama-index.

    Args:
        query: The query to search for (e.g. "Chroma DB")
        library: The library to search in (e.g. "langchain")

    Returns:
        Text from the documentation pages.
    """
    if library not in docs_urls:
        raise ValueError(f"Library '{library}' not supported. Choose from: {', '.join(docs_urls.keys())}")

    search_query = f"site:{docs_urls[library]} {query}"
    results = await search_web(search_query)

    if not results.get("organic"):
        return "No documentation results found."

    combined_text = ""
    for result in results["organic"]:
        combined_text += await fetch_url(result["link"])
    return combined_text[:8000]  # Limit return size if needed

# Entry point
if __name__ == "__main__":
    mcp.run(transport="stdio")
