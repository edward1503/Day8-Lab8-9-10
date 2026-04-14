# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Duy Minh Hoàng  
**MSSV:** 2A202600155  
**Vai trò trong nhóm:** Supervisor Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`
- Functions tôi implement: `supervisor_node()`, `route_decision()`, `make_initial_state()`, `build_graph()`
- File hỗ trợ: `build_index.py` (script khởi tạo ChromaDB index), `test_routing.py` (script kiểm tra routing accuracy)

**Mô tả công việc:**

Tôi chịu trách nhiệm toàn bộ Sprint 1 — refactor RAG pipeline từ monolith sang Supervisor-Worker graph. Cụ thể, tôi thiết kế `AgentState` (shared state schema với 17 fields), implement logic routing trong `supervisor_node()` sử dụng keyword matching theo 4 tầng ưu tiên, và kết nối graph flow `supervisor → route → [retrieval | policy_tool | human_review] → synthesis → END`.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Output của `supervisor_node()` (gồm `supervisor_route`, `route_reason`, `needs_tool`, `risk_high`) quyết định Worker nào sẽ được gọi tiếp theo. Tất cả workers ở Sprint 2 đều phụ thuộc vào state schema mà tôi thiết kế. Nếu routing sai, toàn bộ pipeline sẽ trả lời sai bất kể worker có tốt đến đâu.

**Bằng chứng:** Commit trong `graph.py` — toàn bộ function `supervisor_node()` từ dòng 80–181.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Sử dụng tiered keyword matching thay vì LLM classifier cho routing logic trong supervisor.

**Lý do:**

Tôi chọn keyword matching 4 tầng ưu tiên thay vì gọi LLM để phân loại intent vì 3 lý do:

1. **Tốc độ:** Keyword matching chạy trong ~0ms, trong khi LLM classifier mất ~500-1500ms mỗi lần route. Với 15 test questions + 10 grading questions, tiết kiệm ~25 giây tổng thời gian.
2. **Đủ chính xác:** Bài toán chỉ có 5 tài liệu nội bộ với domain rõ ràng. Keyword matching đạt 15/15 (100%) trên test set — LLM classifier không thể cải thiện hơn.
3. **Reproducible:** Keyword matching cho kết quả deterministic, dễ debug. LLM có thể cho kết quả khác nhau giữa các lần chạy.

**Trade-off đã chấp nhận:**

Nếu domain mở rộng (thêm nhiều tài liệu, câu hỏi phức tạp hơn), keyword matching sẽ khó scale. Khi đó cần chuyển sang LLM classifier hoặc embedding-based intent detection.

**Bằng chứng từ trace/code:**

```
▶ Query: Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?
  Route   : policy_tool_worker
  Reason  : task contains policy/access keywords: [cấp quyền, level 3]
            + SLA context [p1] → multi-hop policy+retrieval
            | risk_high flagged: [khẩn cấp]
  Latency : 0ms
```

Routing đúng, reason chi tiết, latency gần 0 — không cần thêm LLM call.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Routing sai cho câu hỏi refund factual đơn giản (q02) và câu ERR code (q09).

**Symptom:**

Ban đầu, routing logic v1 đạt 13/15 test questions. Cụ thể:
- q02 `"Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?"` bị route sang `policy_tool_worker` (expected: `retrieval_worker`) — vì keyword `"hoàn tiền"` trigger policy route.
- q09 `"ERR-403-AUTH là lỗi gì?"` bị route sang `human_review` (expected: `retrieval_worker`) — vì ERR regex match trigger human review.

**Root cause:**

1. **q02:** Keyword `"hoàn tiền"` quá generic — câu hỏi chỉ hỏi factual info ("bao nhiêu ngày?") chứ không hỏi exception hay policy check.
2. **q09:** ERR code tự động trigger human_review quá sớm — pipeline nên thử retrieval trước rồi abstain nếu không tìm thấy.

**Cách sửa:**

1. Tách `"hoàn tiền"` ra khỏi `policy_exception_keywords`, thay bằng combo check: `"hoàn tiền"` chỉ trigger policy khi đi kèm action signal (`"được không"`, `"có được"`, `"xử lý hoàn"`...). Câu q02 không có action signal → về retrieval.
2. Thu hẹp điều kiện `human_review`: chỉ trigger khi ERR code + ambiguity signal (`"không rõ"`, `"không hiểu"`). q09 hỏi tường minh "là lỗi gì" → không ambiguous → về retrieval.

**Bằng chứng trước/sau:**

```
TRƯỚC: 13/15 passed — q02 ❌ (policy_tool_worker), q09 ❌ (human_review)
SAU:   15/15 passed — q02 ✅ (retrieval_worker), q09 ✅ (retrieval_worker)
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**

Thiết kế routing logic kỹ lưỡng với 4 tầng ưu tiên rõ ràng, đạt 100% accuracy trên test set. Route reason chi tiết, bao gồm danh sách keywords matched, giúp debug dễ dàng. Viết script test tự động (`test_routing.py`) để verify nhanh thay vì kiểm tra thủ công.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Chưa kịp tích hợp thực tế với LLM trong synthesis worker. Routing logic hiện tại dựa hoàn toàn vào keyword — nếu grading questions dùng cách diễn đạt khác (paraphrase) thì có thể miss.

**Nhóm phụ thuộc vào tôi ở đâu?**

Toàn bộ state schema (`AgentState`) và graph flow do tôi thiết kế. Workers ở Sprint 2 phải đọc/ghi đúng các fields tôi đã định nghĩa. Nếu tôi thay đổi schema, tất cả workers phải update theo.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi cần Worker Owner implement `retrieval.py`, `policy_tool.py`, `synthesis.py` để thay thế các placeholder nodes hiện tại trong `graph.py`.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ thêm **confidence-based HITL trigger** vào supervisor: nếu `confidence < 0.4` sau synthesis, tự động trigger `human_review` cho lần chạy tiếp theo với cùng câu hỏi. Lý do: trace cho thấy một số câu abstain (q09) vẫn có confidence = 0.75 (placeholder) — cần confidence thực tế từ synthesis worker để có tín hiệu đáng tin cậy hơn cho HITL.

---

*File này lưu tại: `reports/individual/nguyen_duy_minh_hoang.md`*
