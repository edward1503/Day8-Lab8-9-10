# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Lê Minh Luân  
**MSSV:** 2A202600398  
**Vai trò trong nhóm:** MCP Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `mcp_server.py`, `mcp_client.py` (mới), `mcp_protocol.py` (mới), `mcp_http_server.py` (mới)
- Functions tôi implement: `dispatch_tool()`, `list_tools()`, `_call_mcp_tool()` (refactor), `MCPClient.dispatch()`, `InProcessTransport.call()`, `HttpTransport.call()`, `_extract_ticket_id()`

**Mô tả công việc:**

Tôi chịu trách nhiệm toàn bộ Sprint 3 — thiết kế và triển khai lớp Client-Server MCP (Model Context Protocol). Cụ thể, tôi tạo `mcp_protocol.py` định nghĩa protocol envelope (`MCPRequest`, `MCPResponse`, `MCPError`, `MCPContext`), `mcp_client.py` implement `MCPClient` với transport pluggable (InProcess và HTTP), và `mcp_http_server.py` expose toàn bộ MCP tools qua REST API (FastAPI). Ngoài ra, tôi refactor `workers/policy_tool.py` để thay thế direct import bằng `MCPClient`.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

`policy_tool_worker` (Sprint 2 — Worker Owner) gọi MCP tools thông qua `_call_mcp_tool()`. Sau khi tôi refactor, function này dùng `MCPClient` thay vì import thẳng `mcp_server`. Điều này cho phép đổi transport (InProcess vs. HTTP) mà không cần Worker Owner thay đổi bất kỳ logic nào. `graph.py` của Supervisor Owner không bị ảnh hưởng vì giao diện `run(state)` của workers giữ nguyên.

**Bằng chứng:** Các file mới tạo: `mcp_protocol.py`, `mcp_client.py`, `mcp_http_server.py`; diff trong `workers/policy_tool.py` — thay `from mcp_server import dispatch_tool` bằng `from mcp_client import get_client`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Thiết kế `MCPClient` với **pluggable transport** thay vì hard-code một cách giao tiếp duy nhất.

**Lý do:**

Trong Sprint 2, `policy_tool.py` gọi MCP bằng cách import thẳng: `from mcp_server import dispatch_tool`. Đây là in-process call, không phải client-server thật sự — không có network boundary, không có protocol envelope, và không thể chạy MCP server như một microservice riêng. Tôi có hai lựa chọn:

1. **Option A:** Chỉ wrap `dispatch_tool()` trong một class mỏng — đơn giản nhưng vẫn bị lock vào in-process, không scale được.
2. **Option B (chọn):** Tách transport ra khỏi client logic bằng abstract class `MCPTransport`. `InProcessTransport` gọi trực tiếp, `HttpTransport` gọi qua HTTP POST. Toàn bộ worker chỉ biết `MCPClient.dispatch(MCPRequest)` — không quan tâm transport nào đang chạy.

Quyết định này quan trọng vì cho phép chuyển đổi từ in-process sang HTTP (microservice-ready) chỉ bằng một biến môi trường `MCP_TRANSPORT=http`, không cần sửa code worker.

**Trade-off đã chấp nhận:**

Thêm một lớp abstraction tăng độ phức tạp (3 file mới thay vì 1). Với lab nhỏ, InProcess là đủ. Nhưng khi scale lên production, lợi ích về tách biệt process và khả năng scale độc lập vượt trội hơn chi phí.

**Bằng chứng từ trace/code:**

```python
# BEFORE (Sprint 2) — direct import, tight coupling:
from mcp_server import dispatch_tool
result = dispatch_tool("search_kb", {"query": task})

# AFTER (Sprint 3) — MCPClient, transport-agnostic:
from mcp_client import get_client
from mcp_protocol import MCPRequest, MCPContext

client = get_client()
response = client.dispatch(MCPRequest(
    tool_name="search_kb",
    tool_input={"query": task, "top_k": 3},
    context=MCPContext(run_id=state["run_id"], caller="policy_tool_worker"),
))
if response.is_ok():
    chunks = response.output["chunks"]
```

Smoke test output từ `python3 mcp_client.py`:
```
Transport: inprocess
🎫 Test: get_ticket_info
  status: success | latency: 0ms
  ticket: IT-9847 | priority: P1
❌ Test: nonexistent_tool
  status: error
  error.code: TOOL_EXEC_FAILED
✅ MCPClient Sprint 3 smoke test done (transport=inprocess).
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** `policy_tool.py` hardcode ticket ID `"P1-LATEST"` khi gọi `get_ticket_info` qua MCP.

**Symptom (pipeline làm gì sai?):**

Khi bất kỳ câu hỏi nào có từ `"ticket"`, `"p1"`, hoặc `"jira"`, pipeline luôn gọi `get_ticket_info(ticket_id="P1-LATEST")` — bất kể user đang hỏi về ticket nào. Nếu user hỏi về `IT-1234` hay `P2-SOMETICKET`, pipeline vẫn trả về thông tin của `IT-9847` (API Gateway down). Đây là bug logic nghiêm trọng vì kết quả trả về không grounded vào câu hỏi thực tế.

**Root cause (lỗi nằm ở đâu):**

Dòng 281 trong `workers/policy_tool.py` (Sprint 2):
```python
mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
```
Ticket ID bị hardcode thay vì được extract động từ nội dung câu hỏi.

**Cách sửa:**

Thêm function `_extract_ticket_id(task: str) -> str` dùng regex để tìm pattern ticket ID trong câu hỏi:
```python
def _extract_ticket_id(task: str) -> str:
    match = re.search(r"\b(P\d-\w+|IT-\d{3,6})\b", task, re.IGNORECASE)
    return match.group().upper() if match else "P1-LATEST"
```
Fallback về `"P1-LATEST"` chỉ khi không tìm thấy ticket ID nào trong task.

**Bằng chứng trước/sau:**

```
TRƯỚC:
  task = "Ticket IT-1234 đang ở trạng thái gì?"
  → _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})  ❌
  → Trả về: IT-9847 (API Gateway down) — SAI ticket!

SAU:
  ticket_id = _extract_ticket_id(task)  # → "IT-1234"
  → _call_mcp_tool("get_ticket_info", {"ticket_id": "IT-1234"})  ✅
  → history: "[policy_tool_worker] called MCP get_ticket_info (ticket_id=IT-1234)"
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**

Thiết kế protocol envelope (`MCPRequest`/`MCPResponse`/`MCPError`) rõ ràng và đầy đủ — mỗi call đều có `request_id` để trace, `latency_ms` để đo hiệu năng, và `error.code` có cấu trúc thay vì raw exception. Việc tách `MCPTransport` thành abstract class giúp code dễ test và dễ swap (InProcess → HTTP chỉ cần đổi env var).

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Chưa implement schema validation: `dispatch_tool()` hiện nhận `**tool_input` trực tiếp mà không validate theo `inputSchema` đã khai báo trong `TOOL_SCHEMAS`. Nếu worker gọi sai tham số, lỗi chỉ phát hiện ở runtime (TypeError), không phải ở boundary MCP.

**Nhóm phụ thuộc vào tôi ở đâu?**

`policy_tool_worker` phụ thuộc vào `mcp_client.py` để gọi tools. Nếu `MCPClient` chưa hoạt động, worker không thể fetch context bổ sung (ticket info, KB search) — kết quả policy analysis sẽ kém chính xác hơn.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi cần `mcp_server.py` từ Sprint 2 (Worker Owner) đã implement đủ 4 tools để `InProcessTransport` có thể dispatch đúng. Ngoài ra, `HttpTransport` chỉ có ý nghĩa khi Trace & Docs Owner chạy `eval_trace.py` và cần tách MCP Server ra process riêng.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ thêm **JSON Schema validation vào `dispatch_tool()`**: trước khi gọi tool function, validate `tool_input` với `inputSchema` từ `TOOL_SCHEMAS`. Lý do: smoke test của `mcp_client.py` cho thấy khi gọi `nonexistent_tool`, lỗi được catch đúng — nhưng khi gọi `check_access_permission` thiếu `access_level`, lỗi là `TypeError` từ Python, không phải `MCPError(code="INVALID_INPUT")`. Điều này làm khó debug từ phía worker vì không phân biệt được lỗi input vs. lỗi logic tool.

---

*File này lưu tại: `reports/individual/nguyen_le_minh_luan.md`*
