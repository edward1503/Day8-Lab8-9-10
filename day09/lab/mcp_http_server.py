"""
mcp_http_server.py — MCP over HTTP using FastAPI (Sprint 3 — Advanced/Bonus)

Exposes mcp_server tools via a real HTTP REST API.
Enables workers to call MCP tools over the network instead of in-process.

Run this server:
    pip install fastapi uvicorn
    uvicorn mcp_http_server:app --reload --port 8000

Then switch workers to HTTP transport:
    MCP_TRANSPORT=http MCP_SERVER_URL=http://localhost:8000 python graph.py

API Endpoints:
    GET  /health         → health check + tool count
    GET  /tools          → list all available tools (MCP discovery)
    POST /tools/call     → execute a tool (MCP execution)
    GET  /tools/{name}   → get schema for a specific tool

Protocol format for POST /tools/call:
    Request body (MCPRequest JSON):
    {
        "request_id": "uuid4-optional",
        "protocol_version": "1.0",
        "tool_name": "search_kb",
        "tool_input": {"query": "SLA P1", "top_k": 3},
        "context": {"run_id": "run_001", "caller": "policy_tool_worker"}
    }

    Response body (MCPResponse JSON):
    {
        "request_id": "...",
        "protocol_version": "1.0",
        "tool_name": "search_kb",
        "status": "success",
        "output": {"chunks": [...], "sources": [...], "total_found": 3},
        "error": null,
        "latency_ms": 42
    }
"""

import time
import uuid
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError(
        "FastAPI required for HTTP server mode.\n"
        "Install with: pip install fastapi uvicorn\n"
        "Or run: pip install -r requirements.txt"
    )

# Import the existing mcp_server tool registry (no changes to mcp_server.py needed)
from mcp_server import dispatch_tool, list_tools, TOOL_SCHEMAS


# ─────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────

app = FastAPI(
    title="MCP Server — Day09 Lab (HTTP Mode)",
    description=(
        "Model Context Protocol server exposed over HTTP.\n\n"
        "Workers connect via HttpTransport in mcp_client.py "
        "by setting MCP_TRANSPORT=http."
    ),
    version="1.0",
)


# ─────────────────────────────────────────────────────
# Pydantic request/response models (HTTP layer)
# These mirror mcp_protocol.py dataclasses but use Pydantic for validation.
# ─────────────────────────────────────────────────────

class MCPContextModel(BaseModel):
    run_id: Optional[str] = None
    caller: Optional[str] = None
    timestamp: Optional[str] = None


class ToolCallRequest(BaseModel):
    """HTTP request body for POST /tools/call"""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    protocol_version: str = "1.0"
    tool_name: str
    tool_input: Dict[str, Any]
    context: Optional[MCPContextModel] = None

    class Config:
        json_schema_extra = {
            "example": {
                "tool_name": "search_kb",
                "tool_input": {"query": "SLA P1 resolution time", "top_k": 3},
                "context": {"run_id": "run_001", "caller": "policy_tool_worker"},
            }
        }


class MCPErrorModel(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ToolCallResponse(BaseModel):
    """HTTP response body for POST /tools/call"""
    request_id: str
    protocol_version: str = "1.0"
    tool_name: str
    status: str  # "success" | "error"
    output: Optional[Dict[str, Any]] = None
    error: Optional[MCPErrorModel] = None
    latency_ms: Optional[int] = None


# ─────────────────────────────────────────────────────
# Request logging middleware
# ─────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and their latency."""
    start = time.time()
    response = await call_next(request)
    latency = int((time.time() - start) * 1000)
    print(f"[MCP HTTP] {request.method} {request.url.path} → {response.status_code} ({latency}ms)")
    return response


# ─────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint. Returns server status and tool count."""
    return {
        "status": "ok",
        "service": "mcp-server",
        "protocol_version": "1.0",
        "tools_count": len(TOOL_SCHEMAS),
        "tools": list(TOOL_SCHEMAS.keys()),
    }


@app.get("/tools", tags=["MCP"])
def get_tools():
    """
    MCP tools/list — Discover all available tools.

    Equivalent to MCP spec's `tools/list` request.
    Returns tool schemas including inputSchema and outputSchema.
    """
    return {"tools": list_tools()}


@app.get("/tools/{tool_name}", tags=["MCP"])
def get_tool_schema(tool_name: str):
    """Get schema for a specific tool by name."""
    if tool_name not in TOOL_SCHEMAS:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "TOOL_NOT_FOUND",
                "message": f"Tool '{tool_name}' is not registered.",
                "available_tools": list(TOOL_SCHEMAS.keys()),
            },
        )
    return TOOL_SCHEMAS[tool_name]


@app.post("/tools/call", response_model=ToolCallResponse, tags=["MCP"])
def call_tool(body: ToolCallRequest):
    """
    MCP tools/call — Execute a tool by name.

    Equivalent to MCP spec's `tools/call` request.
    Returns a structured MCPResponse with status, output, and error fields.
    """
    start = time.time()
    request_id = body.request_id

    # Caller info for logging
    caller_info = ""
    if body.context:
        parts = []
        if body.context.caller:
            parts.append(f"caller={body.context.caller}")
        if body.context.run_id:
            parts.append(f"run_id={body.context.run_id[:16]}")
        if parts:
            caller_info = f" [{', '.join(parts)}]"

    print(f"[MCP HTTP] tool={body.tool_name}{caller_info} input={list(body.tool_input.keys())}")

    # Execute tool
    raw_output = dispatch_tool(body.tool_name, body.tool_input)
    latency_ms = int((time.time() - start) * 1000)

    # Check for error signal from dispatch_tool ({"error": "..."} pattern)
    if isinstance(raw_output, dict) and "error" in raw_output and len(raw_output) == 1:
        print(f"[MCP HTTP] tool={body.tool_name} → ERROR: {raw_output['error']}")
        return ToolCallResponse(
            request_id=request_id,
            protocol_version=body.protocol_version,
            tool_name=body.tool_name,
            status="error",
            error=MCPErrorModel(
                code="TOOL_EXEC_FAILED",
                message=str(raw_output["error"]),
            ),
            latency_ms=latency_ms,
        )

    print(f"[MCP HTTP] tool={body.tool_name} → success ({latency_ms}ms)")
    return ToolCallResponse(
        request_id=request_id,
        protocol_version=body.protocol_version,
        tool_name=body.tool_name,
        status="success",
        output=raw_output,
        latency_ms=latency_ms,
    )


# ─────────────────────────────────────────────────────
# Run directly (dev mode)
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("MCP HTTP Server — Sprint 3 (Advanced / Bonus)")
    print("=" * 60)
    print("\nStarting FastAPI server on http://localhost:8000")
    print("Docs: http://localhost:8000/docs")
    print("Health: http://localhost:8000/health")
    print("Tools: http://localhost:8000/tools")
    print("\nTo use with workers:")
    print("  MCP_TRANSPORT=http MCP_SERVER_URL=http://localhost:8000 python graph.py")
    print("\nPress Ctrl+C to stop.\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
