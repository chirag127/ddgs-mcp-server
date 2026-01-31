
import json
import logging
from typing import Optional, Literal
from mcp.server import Server
import mcp.types as types
from ddgs import DDGS

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ddgs-mcp")

# MCP Server
server = Server("ddgs-mcp-server")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_text",
            description="Perform a metasearch using various backends (DuckDuckGo, Google, Bing, etc.). Use this to find APIs, libraries, developer tools, and general information.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "backend": {
                        "type": "string",
                        "enum": ["auto", "html", "lite", "bing", "brave", "duckduckgo", "google", "grokipedia", "mojeek", "yandex", "yahoo", "wikipedia"],
                        "default": "auto",
                        "description": "Search engine backend to use."
                    },
                    "region": {"type": "string", "default": "us-en", "description": "e.g., us-en, uk-en"},
                    "safesearch": {"type": "string", "enum": ["on", "moderate", "off"], "default": "moderate"},
                    "timelimit": {"type": "string", "enum": ["d", "w", "m", "y"], "default": None},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="search_news",
            description="Perform a news search to find the latest updates, releases, or security alerts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "region": {"type": "string", "default": "us-en"},
                    "safesearch": {"type": "string", "default": "moderate"},
                    "timelimit": {"type": "string", "default": None},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    logger.info(f"Calling tool: {name} with args: {arguments}")

    if name not in ["search_text", "search_news"]:
        raise ValueError(f"Unknown tool: {name}")

    query = arguments.get("query")
    backend = arguments.get("backend", "auto")
    region = arguments.get("region", "us-en")
    safesearch = arguments.get("safesearch", "moderate")
    timelimit = arguments.get("timelimit")
    max_results = arguments.get("max_results", 10)

    try:
        with DDGS() as ddgs:
            results = []
            if name == "search_text":
                results = ddgs.text(
                    query=query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=max_results,
                    backend=backend
                )
            elif name == "search_news":
                results = ddgs.news(
                    query=query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=max_results
                )

            return [types.TextContent(type="text", text=json.dumps(results, indent=2))]

    except Exception as e:
        logger.error(f"Error executing {name}: {e}")
        return [types.TextContent(type="text", text=f"Error performing search: {str(e)}")]
