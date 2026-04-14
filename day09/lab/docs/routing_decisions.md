# Routing Decisions Log — Lab Day 09

**Nhóm:** Day09-Lab8-9-10  
**Ngày:** 2026-04-14

> Dữ liệu được tổng hợp từ trace thật trong `artifacts/traces/` (latest run cho 15 câu hỏi `q01..q15`).

---

## Routing Decision #1

**Task đầu vào:**
> Ai phải phê duyệt để cấp quyền Level 3? (`q03`)

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keywords: [cấp quyền, level 3]`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** `policy_tool_worker -> retrieval_worker -> synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Level 3 cần Line Manager + IT Admin + IT Security.
- confidence: `0.56`
- Correct routing? **Yes**

**Nhận xét:**  
Câu hỏi mang tính policy/access nên route vào `policy_tool_worker` là đúng. Dù MCP HTTP thất bại, hệ vẫn fallback retrieval + synthesis và trả lời đúng nhờ evidence từ `access_control_sop.txt`.

---

## Routing Decision #2

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý? (`q09`)

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `no specific policy/SLA signal detected — default to knowledge base retrieval`  
**MCP tools được gọi:** `[]`  
**Workers called sequence:** `retrieval_worker -> synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Không đủ thông tin trong tài liệu nội bộ, đề xuất liên hệ team phụ trách.
- confidence: `0.30`
- Correct routing? **Yes**

**Nhận xét:**  
Đây là câu abstain/insufficient-context; route retrieval mặc định là hợp lý để xác nhận không có evidence. Confidence thấp (0.30) phản ánh đúng mức độ chắc chắn.

---

## Routing Decision #3

**Task đầu vào:**
> Ticket P1 lúc 2am, cần Level 2 access tạm thời và notify stakeholders theo SLA. (`q15`)

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keywords: [level 2] + SLA context [p1, sla, ticket] -> multi-hop policy+retrieval | risk_high flagged: [emergency, 2am, tạm thời]`  
**MCP tools được gọi:** `search_kb`, `get_ticket_info`  
**Workers called sequence:** `policy_tool_worker -> retrieval_worker -> synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): Trả đủ 2 luồng (Level 2 temporary access + SLA notification/escalation).
- confidence: `0.61`
- Correct routing? **Yes**

**Nhận xét:**  
Đây là câu multi-hop khó nhất, route reason có cả domain signal và risk signal nên trace rất dễ debug. Pipeline gọi đủ 3 workers và giữ được cấu trúc câu trả lời theo 2 quy trình.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 9 | 60% |
| policy_tool_worker | 6 | 40% |
| human_review | 0 | 0% |

### Routing Accuracy

- Câu route đúng: **15 / 15**
- Câu route sai (đã sửa bằng cách nào?): **0**
- Câu trigger HITL: **0**

### Lesson Learned về Routing

1. Rule-based keyword routing đủ ổn định cho tập câu hỏi domain hẹp (SLA/Policy/Access).
2. Route reason nên chứa cả keyword hit + risk signal để tăng khả năng debug sau chạy.

### Route Reason Quality

`route_reason` hiện tại đủ để debug nhanh trong đa số trường hợp.  
Cải tiến tiếp theo: thêm `matched_keywords` dạng structured list trong trace JSON để dễ phân tích tự động bằng script.
