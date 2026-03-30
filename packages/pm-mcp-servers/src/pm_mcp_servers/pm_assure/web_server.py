"""SSE web server for pm-assure MCP server.

Allows claude.ai and other remote MCP clients to connect over HTTP.
Run with: uvicorn pm_mcp_servers.pm_assure.web_server:app --host 0.0.0.0 --port 8080

Or: python -m pm_mcp_servers.pm_assure.web_server
"""

from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse

from mcp.server.sse import SseServerTransport

from pm_mcp_servers.unified_server import app as mcp_app


# SSE transport — client connects to /sse, posts messages to /messages/
sse_transport = SseServerTransport("/messages/")


async def handle_sse(request):
    """SSE endpoint — client establishes long-lived connection here."""
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_app.run(
            read_stream,
            write_stream,
            mcp_app.create_initialization_options(),
        )


async def handle_messages(request):
    """Message endpoint — client POSTs tool calls here."""
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )


async def health(request):
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "server": "pda-platform", "transport": "sse", "tools": 29})


# Build Starlette app
app = Starlette(
    routes=[
        Route("/health", health),
        Route("/sse", handle_sse),
        Mount("/messages/", app=sse_transport.handle_post_message),
    ],
)

# CORS — allow claude.ai and any other MCP client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def main():
    """Run the SSE web server."""
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting pm-assure SSE server on port {port}")
    print(f"SSE endpoint: http://localhost:{port}/sse")
    print(f"Health check: http://localhost:{port}/health")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
