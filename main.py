import asyncio
import sys
from mcp.server.stdio import stdio_server
from server import server

async def main():
    """
    Main entry point for UVX / Stdio usage.
    """
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
