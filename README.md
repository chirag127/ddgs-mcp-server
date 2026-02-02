# DDGS MCP Server

A Model Context Protocol (MCP) server that provides DuckDuckGo Search capabilities to AI agents.

## Features

- **search_text**: Advanced metasearch using `bing`, `brave`, `duckduckgo`, `google`, `mojeek`, `yahoo`, `yandex`, `wikipedia`.
  - **Full Content Extraction**: Optionally fetch complete page content (not just snippets) for comprehensive context.
- **search_news**: Find latest updates, releases, and tech news.

## Full Content Extraction

For coding agents that need complete context from search results, enable full page content fetching:

### Usage

```json
{
  "query": "python async programming tutorial",
  "fetch_full_content": true,
  "max_content_length": 50000,
  "max_results": 5
}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fetch_full_content` | boolean | `false` | Enable full page content extraction |
| `max_content_length` | integer | `50000` | Maximum characters per page (when `fetch_full_content` is true) |

### Response Structure

When `fetch_full_content` is enabled, each result includes a `full_content` field:

```json
[
  {
    "title": "Python Async Programming Guide",
    "href": "https://example.com/python-async",
    "body": "Brief snippet from search results...",
    "full_content": "Complete extracted article text with all paragraphs, code examples, and detailed explanations..."
  }
]
```

### Performance Notes

- Content extraction adds ~1-3 seconds latency per page
- Up to 5 pages are fetched concurrently to minimize total time
- Failed fetches return `[Content extraction failed or blocked]` without breaking the search
- Uses [Trafilatura](https://trafilatura.readthedocs.io/) for high-quality text extraction


## Installation & Usage

You can run this server directly using `uvx` without installing it globally.

### VS Code (Claude Desktop / Cline)

Add this to your MCP settings file (e.g., `cline_mcp_settings.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ddgs-search": {
      "command": "uvx",
      "args": [
        "ddgs-mcp-server"
      ],
      "disabled": false,
      "alwaysAllow": []
    }
  }
}
```

### Manual Execution

```bash
uvx ddgs-mcp-server
```


## Secrets & Configuration

This project technically **does not require API keys** to run locally, as it scrapes DuckDuckGo. However, for **publishing** or **proxy usage**, you should configure your environment.

### 1. Set up Secrets
Copy the example file:
```bash
cp .env.example .env
```

### 2. Required Tokens

| Token | Purpose | How to Get It |
| :--- | :--- | :--- |
| **PyPI API Token** | Publishing to PyPI | 1. Go to [PyPI Account Settings](https://pypi.org/manage/account/token/)<br>2. Select "Add API Token"<br>3. Scope to "Entire account" (for first publish)<br>4. Set as `TWINE_PASSWORD` in `.env` |
| **Proxy URL** | Bypassing Blocks (Optional) | Use any HTTP/SOCKS5 proxy provider if you encounter rate limits. |

## Development / Publishing

To build and publish this package to PyPI (using the secrets from above):

1.  **Build**:
    ```bash
    pip install build twine
    python -m build
    ```

2.  **Publish** (loads secrets from .env if you export them, or prompts you):
    ```bash
    # If using .env variables (PowerShell)
    # $env:TWINE_USERNAME = "__token__"
    # $env:TWINE_PASSWORD = "pypi-..."

    python -m twine upload dist/*
    ```
