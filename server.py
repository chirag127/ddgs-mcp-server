
import asyncio
import json
import logging
import uuid
from typing import Optional, Literal

import httpx
import trafilatura
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

# MCP Imports
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# DDGS Import
from ddgs import DDGS

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ddgs-mcp")

app = FastAPI(title="DDGS MCP Server")

# MCP Server
server = Server("ddgs-mcp-server")

# --- Content Extraction Utilities ---

async def fetch_page_content(
    url: str,
    timeout: int = 10,
    max_length: int = 50000
) -> Optional[str]:
    """
    Fetch and extract main text content from a URL using trafilatura.

    Args:
        url: The URL to fetch content from
        timeout: Request timeout in seconds
        max_length: Maximum characters to return

    Returns:
        Extracted text content or None on failure
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=True
        ) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
            if response.status_code == 200:
                downloaded = response.text
                # Extract main content using trafilatura
                extracted = trafilatura.extract(
                    downloaded,
                    include_links=False,
                    include_images=False,
                    include_comments=False,
                    favor_precision=True
                )
                if extracted:
                    return extracted[:max_length]
    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching {url}")
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
    return None


async def enrich_results_with_content(
    results: list,
    max_concurrent: int = 5,
    max_length: int = 50000
) -> list:
    """
    Fetch full content for all search results concurrently.

    Args:
        results: List of search result dictionaries
        max_concurrent: Maximum concurrent requests
        max_length: Maximum content length per page

    Returns:
        Results list with 'full_content' field added
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_semaphore(result: dict) -> dict:
        async with semaphore:
            url = result.get("href")
            if url:
                content = await fetch_page_content(url, max_length=max_length)
                result["full_content"] = content if content else "[Content extraction failed or blocked]"
            return result

    tasks = [fetch_with_semaphore(r.copy()) for r in results]
    return await asyncio.gather(*tasks)


# --- DDGS Wrappers ---

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_text",
            description="Perform a text search using DuckDuckGo. Use this for general web queries. Optionally fetch full page content for complete context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "region": {"type": "string", "default": "us-en", "description": "e.g., us-en, uk-en"},
                    "safesearch": {"type": "string", "enum": ["on", "moderate", "off"], "default": "moderate"},
                    "timelimit": {"type": "string", "enum": ["d", "w", "m", "y"], "default": None},
                    "max_results": {"type": "integer", "default": 10},
                    "fetch_full_content": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, fetches and returns the full text content of each result page. This provides complete context but adds latency."
                    },
                    "max_content_length": {
                        "type": "integer",
                        "default": 50000,
                        "description": "Maximum characters of content to fetch per page (only used if fetch_full_content is true)."
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="search_images",
            description="Perform an image search using DuckDuckGo.",
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
        ),
        types.Tool(
            name="search_videos",
            description="Perform a video search using DuckDuckGo.",
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
        ),
        types.Tool(
            name="search_news",
            description="Perform a news search using DuckDuckGo.",
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
        ),
         types.Tool(
            name="search_books",
            description="Perform a book search using DuckDuckGo (Anna's Archive backend).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    logger.info(f"Calling tool: {name} with args: {arguments}")

    query = arguments.get("query")
    region = arguments.get("region", "us-en")
    safesearch = arguments.get("safesearch", "moderate")
    timelimit = arguments.get("timelimit")
    max_results = arguments.get("max_results", 10)

    # New parameters for full content extraction
    fetch_full_content = arguments.get("fetch_full_content", False)
    max_content_length = arguments.get("max_content_length", 50000)

    try:
        # Using context manager for DDGS
        with DDGS() as ddgs:
            results = []
            if name == "search_text":
                results = ddgs.text(query=query, region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results)

                # Convert generator to list for manipulation
                results = list(results) if results else []

                # Enrich with full content if requested
                if fetch_full_content and results:
                    logger.info(f"Fetching full content for {len(results)} results...")
                    results = await enrich_results_with_content(
                        results,
                        max_length=max_content_length
                    )
                    logger.info("Full content extraction complete")

            elif name == "search_images":
                results = ddgs.images(query=query, region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results)
                results = list(results) if results else []
            elif name == "search_videos":
                results = ddgs.videos(query=query, region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results)
                results = list(results) if results else []
            elif name == "search_news":
                results = ddgs.news(query=query, region=region, safesearch=safesearch, timelimit=timelimit, max_results=max_results)
                results = list(results) if results else []
            elif name == "search_books":
                # Check for books method availability or fallback
                if hasattr(ddgs, 'books'):
                    results = ddgs.books(query=query, max_results=max_results)
                    results = list(results) if results else []
                else:
                    return [types.TextContent(type="text", text="Error: 'books' search backend not available in this version of python-ddgs.")]
            else:
                raise ValueError(f"Unknown tool: {name}")

            return [types.TextContent(type="text", text=json.dumps(results, indent=2, ensure_ascii=False))]

    except Exception as e:
        logger.error(f"Error executing {name}: {e}")
        return [types.TextContent(type="text", text=f"Error performing search: {str(e)}")]


# --- SSE Transport Integration ---

class SessionManager:
    """Simple in-memory session manager for SSE transports."""
    def __init__(self):
        self.sessions = {}

    def add_session(self, session_id: str, transport: SseServerTransport):
        self.sessions[session_id] = transport

    def get_session(self, session_id: str) -> Optional[SseServerTransport]:
        return self.sessions.get(session_id)

    def remove_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

session_manager = SessionManager()

@app.get("/sse")
async def handle_sse(request: Request):
    import uuid

    # Create a new transport for this connection
    # The endpoint passed here is where the client should send messages (POST)
    # We append the session ID to it so we can route correctly in the /messages handler
    session_id = str(uuid.uuid4())
    transport = SseServerTransport(f"/messages?session_id={session_id}")

    async def sse_generator():
        logger.info(f"New SSE connection: {session_id}")
        session_manager.add_session(session_id, transport)

        try:
            # transport.connect_sse yields (read_stream, write_stream)
            async with transport.connect_sse(request.scope, request.receive, request._send) as streams:
                read_stream, write_stream = streams
                # Run the MCP server for this session
                await server.run(read_stream, write_stream, server.create_initialization_options())
        except Exception as e:
            logger.error(f"SSE session {session_id} error: {e}")
            pass
        finally:
            logger.info(f"Closing SSE connection: {session_id}")
            session_manager.remove_session(session_id)

    return EventSourceResponse(sse_generator())

@app.post("/messages")
async def handle_messages(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id:
        return JSONResponse(status_code=400, content={"error": "Missing session_id"})

    transport = session_manager.get_session(session_id)
    if not transport:
        return JSONResponse(status_code=404, content={"error": "Session not found or expired"})

    # Forward the request logic to the transport
    # transport.handle_post_message processes the request body and pushes to the read stream
    await transport.handle_post_message(request.scope, request.receive, request._send)
    return JSONResponse(content={"status": "ok"})

@app.get("/health")
async def health():
    return {"status": "ok", "active_sessions": len(session_manager.sessions)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
