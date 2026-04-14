# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Nhom_2_zone_1_403  
**Thành viên:**
| Tên | Vai trò | Email |
|-----|---------|-------|
| (Nhóm cập nhật) | Supervisor Owner | N/A |
| (Nhóm cập nhật) | Worker Owner | N/A |
| (Nhóm cập nhật) | MCP Owner | N/A |
| Vu Quang Phuc (2A202600346) | Trace & Docs Owner | N/A |

**Ngày nộp:** 2026-04-14  
**Repo:** `Day8-Lab8-9-10/day09/lab`  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Hướng dẫn nộp group report:**
> 
> - File này nộp tại: `reports/group_report.md`
> - Deadline: Được phép commit **sau 18:00** (xem SCORING.md)
> - Tập trung vào **quyết định kỹ thuật cấp nhóm** — không trùng lặp với individual reports
> - Phải có **bằng chứng từ code/trace** — không mô tả chung chung
> - Mỗi mục phải có ít nhất 1 ví dụ cụ thể từ code hoặc trace thực tế của nhóm

---

## 1. Kiến trúc nhóm đã xây dựng (150–200 từ)

> Mô tả ngắn gọn hệ thống nhóm: bao nhiêu workers, routing logic hoạt động thế nào,
> MCP tools nào được tích hợp. Dùng kết quả từ `docs/system_architecture.md`.

**Hệ thống tổng quan:**

Nhóm triển khai kiến trúc **Supervisor-Worker** cho bài toán trợ lý nội bộ CS/IT Helpdesk. Hệ thống gồm 1 supervisor (`graph.py`) và 3 worker chính: `retrieval_worker`, `policy_tool_worker`, `synthesis_worker`; ngoài ra có nhánh `human_review` (HITL placeholder). Supervisor nhận câu hỏi, phân tích tín hiệu và ghi `route_reason`, `risk_high`, `needs_tool` trước khi route sang worker phù hợp. `retrieval_worker` xử lý semantic retrieval từ ChromaDB, `policy_tool_worker` xử lý domain policy/exception và gọi MCP tools khi cần, còn `synthesis_worker` tạo đáp án grounded có citation và confidence. Toàn bộ quá trình được lưu trace theo run với các trường `workers_called`, `worker_io_logs`, `mcp_tools_used`, `latency_ms`, giúp quan sát và debug rõ theo từng bước.

**Routing logic cốt lõi:**
> Mô tả logic supervisor dùng để quyết định route (keyword matching, LLM classifier, rule-based, v.v.)

Nhóm dùng **rule-based keyword routing** để đảm bảo deterministic behavior: nhóm keyword SLA/ticket route vào `retrieval_worker`; nhóm keyword refund/access/policy route vào `policy_tool_worker`; các trường hợp mã lỗi mơ hồ + thiếu context mới chuyển `human_review`. Cách này giúp route ổn định trong domain hẹp của lab và cho phép audit nhanh qua `route_reason`.

**MCP tools đã tích hợp:**
> Liệt kê tools đã implement và 1 ví dụ trace có gọi MCP tool.

- `search_kb`: Tìm chunk evidence từ KB nội bộ theo query và trả sources để policy worker/synthesis dùng tiếp
- `get_ticket_info`: Tra cứu ticket mock (status/priority/escalation/notifications) để hỗ trợ các câu hỏi sự cố
- `check_access_permission`: Kiểm tra điều kiện cấp quyền theo Access SOP (bao gồm emergency logic cho level 2/3)

---

## 2. Quyết định kỹ thuật quan trọng nhất (200–250 từ)

> Chọn **1 quyết định thiết kế** mà nhóm thảo luận và đánh đổi nhiều nhất.
> Phải có: (a) vấn đề gặp phải, (b) các phương án cân nhắc, (c) lý do chọn phương án đã chọn.

**Quyết định:** Dùng Supervisor-Worker với **keyword rule-based routing + trace-first observability**, thay vì giữ monolithic single-agent hoặc route bằng LLM classifier.

**Bối cảnh vấn đề:**

Bài toán Day 09 có nhiều loại câu khác nhau: SLA, refund policy, access control, multi-hop và insufficient context. Trong Day 08, pipeline monolith trả lời được câu đơn giản nhưng khó debug khi sai vì không có route-level visibility. Nhóm cần một cơ chế vừa dễ vận hành trong thời gian lab, vừa đủ khả năng mở rộng thêm tool call qua MCP.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Giữ single-agent (Day 08 style) | Ít thành phần, latency thấp hơn | Debug khó, không tách trách nhiệm, khó mở rộng tool |
| Multi-agent + LLM route classifier | Linh hoạt ngữ nghĩa, ít phụ thuộc keyword | Không deterministic, tăng cost/latency, khó kiểm soát trong lab |

**Phương án đã chọn và lý do:**

Nhóm chọn **Multi-agent + rule-based route** vì cân bằng được tính ổn định và khả năng mở rộng: supervisor route rõ ràng; worker contract giúp test độc lập; MCP tách capability bên ngoài khỏi core pipeline. Kết quả thực tế: routing đạt 15/15 đúng theo expected route trong tập 15 câu, multi-hop case (`q13`, `q15`) đi đúng chuỗi worker và trả lời đủ ý. Đồng thời trace cho phép khoanh vùng lỗi hạ tầng MCP (`HTTP_TRANSPORT_FAILED`) mà không nhầm thành lỗi logic route.

**Bằng chứng từ trace/code:**
> Dẫn chứng cụ thể (VD: route_reason trong trace, đoạn code, v.v.)

```
[supervisor] route=policy_tool_worker reason=task contains policy/access keywords: [level 2] + SLA context [p1, sla, ticket] -> multi-hop policy+retrieval | risk_high flagged: [emergency, 2am, tạm thời]
[policy_tool_worker] called MCP search_kb
[policy_tool_worker] called MCP get_ticket_info (ticket_id=P1-LATEST)
[retrieval_worker] retrieved 3 chunks from ['access_control_sop.txt', 'sla_p1_2026.txt', 'it_helpdesk_faq.txt']
[synthesis_worker] answer generated, confidence=0.61

Trace source: artifacts/traces/run_20260414_161207.json (q15)
```

---

## 3. Kết quả grading questions (150–200 từ)

> Sau khi chạy pipeline với grading_questions.json (public lúc 17:00):
> - Nhóm đạt bao nhiêu điểm raw?
> - Câu nào pipeline xử lý tốt nhất?
> - Câu nào pipeline fail hoặc gặp khó khăn?

**Tổng điểm raw ước tính:** N/A (chưa có file grading raw score chính thức trong repo hiện tại)

**Câu pipeline xử lý tốt nhất:**
- ID: `q15` (proxy cho multi-hop khó) — Lý do tốt: route đúng nhánh policy + retrieval, answer trả đủ 2 luồng (access emergency + SLA notify/escalation), confidence 0.61.

**Câu pipeline fail hoặc partial:**
- ID: `q09` (insufficient context) — Fail ở đâu: chưa có tài liệu chứa mã lỗi `ERR-403-AUTH`, nên chỉ có thể abstain.  
  Root cause: thiếu evidence trong corpus, không phải lỗi worker logic.

**Câu gq07 (abstain):** Nhóm xử lý thế nào?

Với case abstain, nhóm để pipeline trả về "Không đủ thông tin trong tài liệu nội bộ" và confidence thấp (0.30). Cách xử lý này ưu tiên an toàn, giảm nguy cơ hallucinate khi thiếu context.

**Câu gq09 (multi-hop khó nhất):** Trace ghi được 2 workers không? Kết quả thế nào?

Trace cho thấy có đủ chain worker ở các case multi-hop khó (`policy_tool_worker -> retrieval_worker -> synthesis_worker`). Kết quả tổng hợp ổn, nhưng latency tăng rõ khi có MCP call.

---

## 4. So sánh Day 08 vs Day 09 — Điều nhóm quan sát được (150–200 từ)

> Dựa vào `docs/single_vs_multi_comparison.md` — trích kết quả thực tế.

**Metric thay đổi rõ nhất (có số liệu):**

Metric thay đổi rõ nhất là **routing visibility/debuggability**: Day 08 không có route trace, trong khi Day 09 có `route_reason`, `workers_called`, `worker_io_logs`, `mcp_tools_used`. Ngoài ra Day 09 đo được `mcp_usage_rate=6/15 (40%)`, `avg_confidence=0.49`, `avg_latency=10,471ms`.

**Điều nhóm bất ngờ nhất khi chuyển từ single sang multi-agent:**

Điều bất ngờ là dù MCP HTTP thất bại ở một số run, hệ vẫn giữ được khả năng trả lời nhờ fallback qua retrieval + synthesis. Điều này cho thấy kiến trúc tách worker có độ chịu lỗi tốt hơn kỳ vọng cho bài lab.

**Trường hợp multi-agent KHÔNG giúp ích hoặc làm chậm hệ thống:**

Trường hợp query đơn giản một tài liệu (single-document), multi-agent không tạo khác biệt lớn về chất lượng answer nhưng lại tăng overhead orchestration, khiến latency cao hơn so với single-agent.

---

## 5. Phân công và đánh giá nhóm (100–150 từ)

> Đánh giá trung thực về quá trình làm việc nhóm.

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Supervisor Owner | `graph.py`, routing logic, state orchestration | 1 |
| Worker Owner | `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`, contracts | 2 |
| MCP Owner | `mcp_server.py`, MCP integration trong policy worker | 3 |
| Vu Quang Phuc (2A202600346) | `eval_trace.py`, `docs/*`, `reports/group_report.md`, individual report | 4 |

**Điều nhóm làm tốt:**

Nhóm làm tốt ở việc chia module theo trách nhiệm và bám contract giữa các thành phần. Khi phát sinh lỗi, trace cung cấp đủ dữ liệu để khoanh vùng nhanh. Việc tách docs theo artifact (`system_architecture`, `routing_decisions`, `single_vs_multi`) giúp tổng hợp kết quả rõ ràng.

**Điều nhóm làm chưa tốt hoặc gặp vấn đề về phối hợp:**

Điểm chưa tốt là đồng bộ quy trình git/rebase chưa mượt, từng gặp conflict chồng conflict ở `eval_trace.py` và `eval_report.json`. Ngoài ra, grading raw score chưa được chuẩn hóa thành một báo cáo điểm số tập trung.

**Nếu làm lại, nhóm sẽ thay đổi gì trong cách tổ chức?**

Nếu làm lại, nhóm sẽ chốt quy ước git-flow từ đầu (feature branch -> PR -> squash merge), đồng thời thêm script tự động kiểm tra conflict markers và validate trace schema trước khi commit để giảm lỗi tích lũy.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì? (50–100 từ)

> 1–2 cải tiến cụ thể với lý do có bằng chứng từ trace/scorecard.

Nếu có thêm 1 ngày, nhóm sẽ ưu tiên 2 cải tiến: (1) bổ sung MCP fallback có kiểm soát (HTTP fail -> in-process fallback) vì trace hiện có nhiều `HTTP_TRANSPORT_FAILED`; (2) thêm accuracy scorer tự động theo category (single-hop/multi-hop/abstain) để so sánh Day08/Day09 bằng số liệu nội dung, không chỉ metrics vận hành.

---

*File này lưu tại: `reports/group_report.md`*  
*Commit sau 18:00 được phép theo SCORING.md*
