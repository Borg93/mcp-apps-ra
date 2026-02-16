import argparse
import os

from src import mcp


def main():
    parser = argparse.ArgumentParser(description="Riksarkivet Document Viewer MCP Server")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run with stdio transport (default is HTTP)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "3001")),
        help="Port for HTTP server (default: 3001)",
    )
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        print(f"MCP Server listening on http://localhost:{args.port}/mcp")
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=args.port,
            path="/mcp",
        )


if __name__ == "__main__":
    main()
