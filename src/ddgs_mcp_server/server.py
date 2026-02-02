
import json
import logging
import asyncio
from typing import Optional

import httpx
import trafilatura
from mcp.server import Server
import mcp.types as types
from ddgs import DDGS

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ddgs-mcp")

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


# --- MCP Tool Definitions ---

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_text",
            description="Perform a metasearch using various backends (DuckDuckGo, Google, Bing, etc.). Use this to find APIs, libraries, developer tools, and general information. Optionally fetch full page content for complete context.",
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

    # New parameters for full content extraction
    fetch_full_content = arguments.get("fetch_full_content", False)
    max_content_length = arguments.get("max_content_length", 50000)

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

            elif name == "search_news":
                results = ddgs.news(
                    query=query,
                    region=region,
                    safesearch=safesearch,
                    timelimit=timelimit,
                    max_results=max_results
                )
                results = list(results) if results else []

            return [types.TextContent(type="text", text=json.dumps(results, indent=2))]

    except Exception as e:
        logger.error(f"Error executing {name}: {e}")
        return [types.TextContent(type="text", text=f"Error performing search: {str(e)}")]
