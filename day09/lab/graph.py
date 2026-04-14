"""
graph.py — Supervisor Orchestrator
Sprint 1: Implement AgentState, supervisor_node, route_decision và kết nối graph.

Kiến trúc:
    Input → Supervisor → [retrieval_worker | policy_tool_worker | human_review] → synthesis → Output

Chạy thử:
    python graph.py
"""

import json
import os
from datetime import datetime
from typing import TypedDict, Literal, Optional

# Uncomment nếu dùng LangGraph:
# from langgraph.graph import StateGraph, END

# ─────────────────────────────────────────────
# 1. Shared State — dữ liệu đi xuyên toàn graph
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    task: str                           # Câu hỏi đầu vào từ user

    # Supervisor decisions
    route_reason: str                   # Lý do route sang worker nào
    risk_high: bool                     # True → cần HITL hoặc human_review
    needs_tool: bool                    # True → cần gọi external tool qua MCP
    hitl_triggered: bool                # True → đã pause cho human review

    # Worker outputs
    retrieved_chunks: list              # Output từ retrieval_worker
    retrieved_sources: list             # Danh sách nguồn tài liệu
    policy_result: dict                 # Output từ policy_tool_worker
    mcp_tools_used: list                # Danh sách MCP tools đã gọi

    # Final output
    final_answer: str                   # Câu trả lời tổng hợp
    sources: list                       # Sources được cite
    confidence: float                   # Mức độ tin cậy (0.0 - 1.0)

    # Trace & history
    history: list                       # Lịch sử các bước đã qua
    workers_called: list                # Danh sách workers đã được gọi
    worker_io_logs: list                # Log chi tiết của từng worker (input/output)
    supervisor_route: str               # Worker được chọn bởi supervisor
    latency_ms: Optional[int]           # Thời gian xử lý (ms)
    run_id: str                         # ID của run này
    timestamp: str                      # Thời điểm thực thi


def make_initial_state(task: str) -> AgentState:
    """Khởi tạo state cho một run mới."""
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "worker_io_logs": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%md_%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────
# 2. Supervisor Node — quyết định route
# ─────────────────────────────────────────────

def _rule_based_supervisor(task: str) -> dict:
    """Fallback logic dựa trên keyword matching."""
    task_lower = task.lower()
    
    # Keyword sets
    policy_exception_keywords = ["flash sale", "store credit", "ngoại lệ", "exception", "license key", "kỹ thuật số", "không được hoàn"]
    access_keywords = ["cấp quyền", "access level", "level 2", "level 3", "level 4", "quyền truy cập", "quyền tạm thời"]
    refund_action_signals = ["được không", "được hoàn", "có được", "xử lý hoàn"]
    sla_keywords = ["p1", "p2", "p3", "p4", "sla", "ticket", "escalation", "sự cố", "on-call"]
    risk_keywords = ["emergency", "khẩn cấp", "2am", "3am", "ngoài giờ", "urgent", "critical"]

    matched_exception = [kw for kw in policy_exception_keywords if kw in task_lower]
    matched_access = [kw for kw in access_keywords if kw in task_lower]
    matched_sla = [kw for kw in sla_keywords if kw in task_lower]
    matched_risk = [kw for kw in risk_keywords if kw in task_lower]

    has_refund_word = any(kw in task_lower for kw in ["hoàn tiền", "refund"])
    has_refund_action = any(kw in task_lower for kw in refund_action_signals)
    refund_policy_trigger = has_refund_word and has_refund_action

    route = "retrieval_worker"
    risk_high = bool(matched_risk)
    needs_tool = False

    if matched_exception or matched_access or refund_policy_trigger:
        route = "policy_tool_worker"
        needs_tool = True
    elif matched_sla:
        route = "retrieval_worker"
    
    return {
        "route": route,
        "reason": f"Rule-based fallback: matched keywords {[kw for kw in (matched_exception + matched_access + matched_sla) if kw in task_lower][:3]}",
        "risk_high": risk_high,
        "needs_tool": needs_tool
    }

def _call_supervisor_llm(task: str) -> dict:
    """Gọi LLM để phân tích và quyết định route."""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = f"""Bạn là bộ não điều phối (Supervisor) của hệ thống IT Helpdesk Multi-Agent. 
Nhiệm vụ: Phân tích yêu cầu người dùng và trả về JSON chỉ định Worker phù hợp.

Workers có sẵn:
1. `retrieval_worker`: Chuyên trả lời các câu hỏi về quy định chung, SLA, HR, hướng dẫn kỹ thuật từ tài liệu.
2. `policy_tool_worker`: Chuyên xử lý các yêu cầu Hoàn tiền (Refund), Cấp quyền truy cập (Access), hoặc các ngoại lệ chính sách cần kiểm tra logic/gọi tool.
3. `human_review`: Dùng khi yêu cầu quá mơ hồ, chứa mã lỗi lạ (ERR-xxx) hoặc cực kỳ rủi ro.

Quy tắc rủi ro (risk_high):
- Đặt `risk_high: true` nếu yêu cầu xảy ra vào giờ nhạy cảm (2am-5am), ghi rõ "emergency", "urgent", "critical", liên quan đến bảo mật hoặc có nguy cơ rò rỉ dữ liệu.

Định dạng trả về (JSON duy nhất):
{{
  "route": "retrieval_worker" | "policy_tool_worker" | "human_review",
  "reason": "Giải thích ngắn gọn lý do chọn route này",
  "needs_tool": true | false,
  "risk_high": true | false
}}

User Task: "{task}"
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "You are a helpful supervisor agent. Output ONLY valid JSON."},
                  {"role": "user", "content": prompt}],
        temperature=0,
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor thông minh: Ưu tiên dùng LLM, fallback về rule-based nếu lỗi.
    Đặc biệt: Nếu phát hiện rủi ro cao (risk_high), ép buộc qua HITL (human_review).
    """
    task = state["task"]
    state["history"].append(f"[supervisor] analyzing task: {task[:80]}...")

    try:
        # 1. Gọi LLM Supervisor
        print(f"  [Orchestration Mode] LLM-based")
        decision = _call_supervisor_llm(task)
        route = decision.get("route", "retrieval_worker")
        reason = decision.get("reason", "LLM decision")
        risk_high = decision.get("risk_high", False)
        needs_tool = decision.get("needs_tool", False)
        state["history"].append(f"[supervisor] LLM decided route={route}")
    except Exception as e:
        # 2. Fallback nếu LLM lỗi
        print(f"  [Orchestration Mode] Rule-based (Fallback)")
        state["history"].append(f"[supervisor] LLM failed ({str(e)}), falling back to rule-based logic")
        decision = _rule_based_supervisor(task)
        route = decision["route"]
        reason = decision["reason"]
        risk_high = decision["risk_high"]
        needs_tool = decision["needs_tool"]

    # 3. Logic ép buộc HITL nếu High Risk (Theo yêu cầu người dùng)
    if risk_high and route != "human_review":
        reason = f"🚨 HIGH RISK DETECTED: {reason} | Redirecting to HITL for safety."
        route = "human_review"
        state["history"].append("[supervisor] High risk detected, forcing human_review")

    # Lưu kết quả vào state
    state["supervisor_route"] = route
    state["route_reason"] = reason
    state["risk_high"] = risk_high
    state["needs_tool"] = needs_tool
    state["history"].append(f"[supervisor] finalized_route={route} reason={reason}")

    return state



# ─────────────────────────────────────────────
# 3. Route Decision — conditional edge
# ─────────────────────────────────────────────

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """
    Trả về tên worker tiếp theo dựa vào supervisor_route trong state.
    Đây là conditional edge của graph.
    """
    route = state.get("supervisor_route", "retrieval_worker")
    return route  # type: ignore


# ─────────────────────────────────────────────
# 4. Human Review Node — HITL placeholder
# ─────────────────────────────────────────────

def human_review_node(state: AgentState) -> AgentState:
    """
    HITL node: pause và chờ human approval.
    Trong lab này, implement dưới dạng placeholder (in ra warning).

    TODO Sprint 3 (optional): Implement actual HITL với interrupt_before hoặc
    breakpoint nếu dùng LangGraph.
    """
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered — awaiting human input")
    state["workers_called"].append("human_review")

    # Placeholder: tự động approve để pipeline tiếp tục
    print(f"\n⚠️  HITL TRIGGERED")
    print(f"   Task: {state['task']}")
    print(f"   Reason: {state['route_reason']}")
    print(f"   Action: Auto-approving in lab mode (set hitl_triggered=True)\n")

    # Sau khi human approve, route về retrieval để lấy evidence
    state["supervisor_route"] = "retrieval_worker"
    state["route_reason"] += " | human approved → retrieval"

    return state


# ─────────────────────────────────────────────
# 5. Import Workers
# ─────────────────────────────────────────────

from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi retrieval worker (Sprint 2)."""
    return retrieval_run(state)


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi policy/tool worker (Sprint 2)."""
    return policy_tool_run(state)


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Wrapper gọi synthesis worker (Sprint 2)."""
    return synthesis_run(state)


# ─────────────────────────────────────────────
# 6. Build Graph
# ─────────────────────────────────────────────

def build_graph():
    """
    Xây dựng graph với supervisor-worker pattern.

    Option A (đơn giản — Python thuần): Dùng if/else, không cần LangGraph.
    Option B (nâng cao): Dùng LangGraph StateGraph với conditional edges.

    Lab này implement Option A theo mặc định.
    TODO Sprint 1: Có thể chuyển sang LangGraph nếu muốn.
    """
    # Option A: Simple Python orchestrator
    def run(state: AgentState) -> AgentState:
        import time
        start = time.time()

        # Step 1: Supervisor decides route
        state = supervisor_node(state)

        # Step 2: Route to appropriate worker
        route = route_decision(state)

        if route == "human_review":
            state = human_review_node(state)
            # After human approval, continue with retrieval
            state = retrieval_worker_node(state)
        elif route == "policy_tool_worker":
            state = policy_tool_worker_node(state)
            # Policy worker may need retrieval context first
            if not state["retrieved_chunks"]:
                state = retrieval_worker_node(state)
        else:
            # Default: retrieval_worker
            state = retrieval_worker_node(state)

        # Step 3: Always synthesize
        state = synthesis_worker_node(state)

        state["latency_ms"] = int((time.time() - start) * 1000)
        state["history"].append(f"[graph] completed in {state['latency_ms']}ms")
        return state

    return run


# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────

_graph = build_graph()


def run_graph(task: str) -> AgentState:
    """
    Entry point: nhận câu hỏi, trả về AgentState với full trace.

    Args:
        task: Câu hỏi từ user

    Returns:
        AgentState với final_answer, trace, routing info, v.v.
    """
    state = make_initial_state(task)
    result = _graph(state)
    return result


def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    """Lưu trace ra file JSON."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return filename


# ─────────────────────────────────────────────
# 8. Manual Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import io, sys
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 60)
    print("Day 09 Lab -- Supervisor-Worker Graph")
    print("=" * 60)

    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
        "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?",
    ]

    for query in test_queries:
        print(f"\n>> Query: {query}")
        result = run_graph(query)
        print(f"  Route   : {result['supervisor_route']}")
        print(f"  Reason  : {result['route_reason']}")
        print(f"  Workers : {result['workers_called']}")
        print(f"  Answer  : {result['final_answer'][:400]}...")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Latency : {result['latency_ms']}ms")

        trace_file = save_trace(result)
        print(f"  Trace   : {trace_file}")

    print("\n[OK] graph.py Sprint 2 wired -- real workers active.")
