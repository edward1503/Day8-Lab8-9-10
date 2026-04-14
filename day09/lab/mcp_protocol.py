"""
mcp_protocol.py — Shared Protocol Types for MCP Client ↔ Server
Sprint 3: Introduce formal MCPRequest / MCPResponse envelope.

This module is the ONLY shared contract between client and server.
Both mcp_client.py and mcp_http_server.py import from here.

TypeScript-equivalent interfaces:

    interface MCPRequest {
        request_id: string;
        protocol_version: string;   // "1.0"
        tool_name: string;
        tool_input: Record<string, any>;
        context?: MCPContext;
    }

    interface MCPContext {
        run_id?: string;
        caller?: string;
        timestamp?: string;
    }

    interface MCPResponse {
        request_id: string;
        protocol_version: string;
        tool_name: string;
        status: "success" | "error";
        output?: Record<string, any>;
        error?: MCPError;
        latency_ms?: number;
    }

    interface MCPError {
        code: string;    // "TOOL_NOT_FOUND" | "INVALID_INPUT" | "EXEC_FAILED" | ...
        message: string;
        details?: any;
    }
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Literal, Optional


# ─────────────────────────────────────────────────────
# MCPContext — optional tracing / caller metadata
# ─────────────────────────────────────────────────────

@dataclass
class MCPContext:
    """
    Optional context passed alongside every MCP request.
    Enables cross-component tracing without polluting tool schemas.

    Fields:
        run_id:    Ties this call to a specific graph run (from AgentState.run_id).
        caller:    Name of the worker/component making the call (e.g. "policy_tool_worker").
        timestamp: ISO 8601 timestamp of when the request was created.
    """
    run_id: Optional[str] = None
    caller: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "caller": self.caller,
            "timestamp": self.timestamp,
        }


# ─────────────────────────────────────────────────────
# MCPRequest — what the client sends
# ─────────────────────────────────────────────────────

@dataclass
class MCPRequest:
    """
    MCP protocol request envelope.

    Equivalent to MCP spec's tools/call message.
    Every tool invocation must be wrapped in this structure.

    Example:
        req = MCPRequest(
            tool_name="search_kb",
            tool_input={"query": "SLA P1", "top_k": 3},
            context=MCPContext(run_id="run_001", caller="policy_tool_worker"),
        )
    """
    tool_name: str
    tool_input: Dict[str, Any]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protocol_version: str = "1.0"
    context: Optional[MCPContext] = None

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict (for HTTP transport)."""
        return {
            "request_id": self.request_id,
            "protocol_version": self.protocol_version,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "context": self.context.to_dict() if self.context else None,
        }


# ─────────────────────────────────────────────────────
# MCPError — structured error payload
# ─────────────────────────────────────────────────────

@dataclass
class MCPError:
    """
    Structured error payload in MCPResponse.

    Error codes (conventions):
        TOOL_NOT_FOUND      Tool name is not registered in the server.
        INVALID_INPUT       Tool input doesn't match the tool's inputSchema.
        EXEC_FAILED         Tool raised an exception during execution.
        TRANSPORT_FAILED    Client-side transport error (network, timeout, etc.).
        HTTP_ERROR          HTTP-level error (4xx/5xx from HttpTransport).
    """
    code: str
    message: str
    details: Any = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# ─────────────────────────────────────────────────────
# MCPResponse — what the server sends back
# ─────────────────────────────────────────────────────

@dataclass
class MCPResponse:
    """
    MCP protocol response envelope.

    status="success" → output is populated.
    status="error"   → error is populated; output is None.

    The request_id echoes the original MCPRequest.request_id for correlation.

    Example (success):
        MCPResponse(
            request_id="abc-123",
            tool_name="search_kb",
            status="success",
            output={"chunks": [...], "sources": [...], "total_found": 3},
            latency_ms=42,
        )

    Example (error):
        MCPResponse(
            request_id="abc-124",
            tool_name="get_ticket_info",
            status="error",
            error=MCPError(code="TOOL_NOT_FOUND", message="Tool 'x' not registered"),
        )
    """
    request_id: str
    tool_name: str
    status: Literal["success", "error"]
    protocol_version: str = "1.0"
    output: Optional[Dict[str, Any]] = None
    error: Optional[MCPError] = None
    latency_ms: Optional[int] = None

    def is_ok(self) -> bool:
        """Convenience check — True when status == 'success'."""
        return self.status == "success"

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "request_id": self.request_id,
            "protocol_version": self.protocol_version,
            "tool_name": self.tool_name,
            "status": self.status,
            "output": self.output,
            "error": self.error.to_dict() if self.error else None,
            "latency_ms": self.latency_ms,
        }


# ─────────────────────────────────────────────────────
# Quick smoke test
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=== MCPRequest ===")
    req = MCPRequest(
        tool_name="search_kb",
        tool_input={"query": "SLA P1", "top_k": 3},
        context=MCPContext(run_id="run_test_001", caller="policy_tool_worker"),
    )
    print(json.dumps(req.to_dict(), indent=2, ensure_ascii=False))

    print("\n=== MCPResponse (success) ===")
    resp_ok = MCPResponse(
        request_id=req.request_id,
        tool_name="search_kb",
        status="success",
        output={"chunks": [], "sources": [], "total_found": 0},
        latency_ms=15,
    )
    print(json.dumps(resp_ok.to_dict(), indent=2, ensure_ascii=False))
    print(f"is_ok: {resp_ok.is_ok()}")

    print("\n=== MCPResponse (error) ===")
    resp_err = MCPResponse(
        request_id=req.request_id,
        tool_name="nonexistent_tool",
        status="error",
        error=MCPError(
            code="TOOL_NOT_FOUND",
            message="Tool 'nonexistent_tool' is not registered.",
        ),
    )
    print(json.dumps(resp_err.to_dict(), indent=2, ensure_ascii=False))
    print(f"is_ok: {resp_err.is_ok()}")

    print("\n✅ mcp_protocol.py — Protocol types OK.")
