# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Đào Anh Quân  
**MSSV:** 2A202600028  
**Vai trò trong nhóm:** Worker Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`
- Functions tôi implement: `retrieve_dense()`, `run()` (retrieval), `_detect_domain()`, `_detect_refund_exceptions()`, `_detect_access_exceptions()`, `_check_temporal_scoping()`, `analyze_policy()`, `run()` (policy), `synthesize()`, `_estimate_confidence()`, `_build_context()`, `_call_llm()`, `run()` (synthesis)

**Mô tả công việc:**

Tôi chịu trách nhiệm toàn bộ Sprint 2 — implement ba workers theo contract đã được Supervisor Owner khai báo trong `AgentState`. Cụ thể: `retrieval_worker` kết nối ChromaDB thực bằng `sentence-transformers`, `policy_tool_worker` phân tích policy theo domain và phát hiện exception, và `synthesis_worker` gọi LLM để tổng hợp câu trả lời có citation dựa trên chunks đã retrieve.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Output của tôi (`retrieved_chunks`, `policy_result`, `final_answer`, `confidence`) là đầu vào cho MCP Owner (Sprint 3) và Trace Owner (Sprint 4). Nếu worker contract sai (sai key trong state), toàn bộ trace log của Sprint 4 sẽ bị thiếu field và mất điểm.

**Bằng chứng:** `workers/retrieval.py` dòng 76–119, `workers/policy_tool.py` dòng 240–289, `workers/synthesis.py`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Tính `confidence` từ cosine similarity thực của ChromaDB thay vì hard-code một giá trị cố định.

**Lý do:**

Khi thiết kế `_estimate_confidence()` trong `synthesis.py`, tôi có hai lựa chọn:

1. **Option A (đơn giản):** Hard-code confidence = 0.8 nếu có chunks, 0.1 nếu không có — nhanh nhưng vô nghĩa về mặt đánh giá chất lượng.
2. **Option B (chọn):** Dùng cosine similarity thực từ ChromaDB làm tín hiệu gốc: `base = 0.6 * max_score + 0.4 * avg_score`. Sau đó cộng citation boost (+0.05 nếu answer có `[1]`, `[2]`) và trừ exception penalty (−0.05 mỗi exception, −0.10 nếu có temporal ambiguity).

Quyết định này giúp confidence phản ánh thực chất chất lượng retrieval. Câu hỏi nằm xa knowledge base sẽ có confidence thấp tự nhiên, giúp hệ thống "honest" thay vì over-confident. Đây cũng là yêu cầu bonus trong SCORING.md.

**Trade-off đã chấp nhận:**

Confidence phụ thuộc vào chất lượng ChromaDB index — nếu index ít chunks hoặc docs chưa normalize tốt, confidence sẽ thấp hơn thực tế năng lực của pipeline.

**Bằng chứng từ code:**

```python
# workers/synthesis.py, hàm _estimate_confidence()
scores = [float(c.get("score", 0.0)) for c in chunks]
avg_score = sum(scores) / len(scores) if scores else 0.0
max_score = max(scores) if scores else 0.0
base = 0.6 * max_score + 0.4 * avg_score

if any(tag in (answer or "") for tag in ["[1]", "[2]", "[3]"]):
    base += 0.05

exceptions = policy_result.get("exceptions_found", []) if policy_result else []
base -= 0.05 * len(exceptions)
```

Kết quả trong eval_report: `avg_confidence = 0.41` — phản ánh đúng chất lượng index, không bị inflate.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** `_detect_domain()` trong `policy_tool.py` ban đầu chỉ xét keyword trong `task` text, bỏ qua `source` filenames của chunks đã retrieve.

**Symptom (pipeline làm gì sai?):**

Câu hỏi `"Ai phê duyệt cấp quyền Level 3?"` được retrieval_worker trả về chunk từ `access_control_sop.txt` với score 0.87. Tuy nhiên, `_detect_domain()` không nhận ra `"level 3"` trong task khớp với `_ACCESS_KEYWORDS` vì cụm `"level 3"` cần match đúng. Kết quả: domain = `"unknown"`, policy_name = `"unknown_policy"`, policy_applies = True (không có exception nào check) — câu trả lời tổng hợp thiếu thông tin về 3 approvers bắt buộc.

**Root cause:**

```python
# TRƯỚC (sai): chỉ xét task text
def _detect_domain(task: str, chunks: list) -> str:
    t = task.lower()
    if any(kw in t for kw in _ACCESS_KEYWORDS):
        return "access_control"
    ...
    return "unknown"
```

Không xét `source` của chunks — retrieval đã tìm đúng doc nhưng policy worker không nhận ra.

**Cách sửa:**

Thêm kiểm tra `source` filenames song song với keyword matching:

```python
# SAU (đúng): xét cả task keywords VÀ source filenames của chunks
sources = {c.get("source", "") for c in chunks if c}
if any(kw in t for kw in _ACCESS_KEYWORDS) or "access_control_sop.txt" in sources:
    return "access_control"
```

**Bằng chứng trước/sau:**

```
TRƯỚC: domain=unknown, policy_name=unknown_policy, exceptions_found=[]
SAU:   domain=access_control, policy_name=access_control_sop,
       exceptions=[no_emergency_bypass_level3]  → policy_applies=False ✅
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**

Thiết kế abstain-first cho synthesis worker: khi `retrieved_chunks = []`, pipeline trả ngay câu mẫu "Không đủ thông tin..." với confidence = 0.1 mà không gọi LLM. Điều này tránh hallucination hoàn toàn cho câu gq07 (câu abstain, 10 điểm). Ngoài ra, `worker_io_logs` được ghi đầy đủ ở cả ba workers, giúp Sprint 4 có trace rõ ràng để phân tích.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

`retrieve_dense()` luôn lấy `top_k=3` cố định — một số câu hỏi multi-hop (như gq09) cần cross-reference 2 docs khác nhau nhưng nếu cả 3 chunks đều từ cùng 1 file thì coverage kém.

**Nhóm phụ thuộc vào tôi ở đâu?**

Toàn bộ giá trị `retrieved_chunks`, `policy_result`, `final_answer`, `confidence` trong trace đến từ ba workers của tôi. Nếu workers trả sai contract, điểm grading bị ảnh hưởng trực tiếp.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi cần Supervisor Owner định nghĩa `needs_tool` trong AgentState để `policy_tool_worker` biết khi nào gọi MCP. Tôi cũng cần MCP Owner (Sprint 3) triển khai `mcp_client.py` để `_call_mcp_tool()` hoạt động qua MCPClient thay vì direct import.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ thêm **diversity filter cho `retrieve_dense()`**: hiện tại top-3 chunks đôi khi đến từ cùng 1 file, giảm coverage multi-hop. Trace câu gq09 (multi-hop P1 + Level 2) cho thấy `retrieved_sources` chỉ có `sla_p1_2026.txt` mà thiếu `access_control_sop.txt` — nếu filter đảm bảo ít nhất 1 chunk từ mỗi source khác nhau, pipeline có thể đạt Full marks câu này thay vì Partial.

---

*File này lưu tại: `reports/individual/dao_anh_quan.md`*