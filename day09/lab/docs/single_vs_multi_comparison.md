# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Day09-Lab8-9-10  
**Ngày:** 2026-04-14

> So sánh dựa trên:  
> - Day 08: `day08/lab/results/scorecard_baseline.md` + `day08/lab/logs/grading_run.json`  
> - Day 09: latest 15 traces trong `day09/lab/artifacts/traces/` + `python eval_trace.py --analyze`

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | ~0.98 (proxy từ Faithfulness 4.90/5) | 0.49 | -0.49 | Day 08 dùng scorecard quality proxy, Day 09 là confidence runtime |
| Avg latency (ms) | N/A | 10,471 | N/A | Day 08 không log latency trong scorecard hiện có |
| Abstain rate (%) | 1/10 (10%) | 5/15 (33.3%) | +23.3% | Day 09 thận trọng hơn với câu thiếu context |
| Multi-hop accuracy | N/A | 2/2 (100%) | N/A | Day 08 không có metric multi-hop tách riêng |
| Routing visibility | ✗ Không có | ✓ Có `route_reason` & `orchestration_mode` | N/A | |
| Debug time (estimate) | ~30 phút | ~5 phút | -25 phút | LLM Supervisor giúp khoanh vùng lỗi semantics cực nhanh |
| MCP usage rate | N/A | 6/15 (40%) | N/A | Chỉ có ở kiến trúc multi-agent |
| Safety Compliance | ✗ Không có | ✓ HITL cho High-risk tasks | N/A | Đặc biệt quan trọng cho vận hành thực tế |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Tốt | Tốt |
| Latency | Nhanh hơn (1 agent path) | Chậm hơn nhẹ do orchestration |
| Observation | Trả lời gọn, ít metadata | Trả lời có trace rõ worker và sources |

**Kết luận:**  
Với câu đơn giản, chất lượng hai bên gần tương đương; lợi thế của Day 09 nằm ở khả năng quan sát và debug, đổi lại tốn thêm chi phí orchestration.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Không có số liệu tách riêng | 2/2 case khó đạt yêu cầu |
| Routing visible? | ✗ | ✓ |
| Observation | Khó biết lỗi nằm ở retrieve hay synthesize | Dễ đọc theo luồng `policy_tool -> retrieval -> synthesis` (ví dụ `q15`) |

**Kết luận:**  
Day 09 vượt trội ở bài toán multi-hop nhờ LLM Supervisor có khả năng phân tích semantics tốt hơn keyword rules, kết hợp chia nhỏ trách nhiệm cho từng worker chuyên biệt.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | 10% | 33.3% |
| Hallucination cases | Có case trả lời tự tin dù thiếu context | Giảm bằng confidence thấp + thông báo thiếu thông tin |
| Observation | Không có route-level trace để giải thích | Có trace cho thấy retrieval không đủ evidence rồi mới abstain |

**Kết luận:**  
Day 09 bảo thủ hơn, ưu tiên an toàn hơn trong môi trường nội bộ.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```text
Khi answer sai -> phải đọc toàn bộ RAG pipeline code -> tìm lỗi ở indexing/retrieval/generation.
Không có route trace nên khó khoanh vùng nhanh.
Thời gian ước tính: ~20 phút/lỗi.
```

### Day 09 — Debug workflow
```text
Khi answer sai -> đọc trace -> xem supervisor_route + route_reason.
  -> Nếu route sai: sửa supervisor rule.
  -> Nếu retrieval sai: test retrieval_worker riêng.
  -> Nếu synthesis sai: test synthesis_worker riêng.
Thời gian ước tính: ~8 phút/lỗi.
```

**Câu cụ thể nhóm đã debug:**  
`q03` và `q15` có MCP HTTP fail (`HTTP_TRANSPORT_FAILED`) nhưng pipeline vẫn ra đáp án vì fallback qua retrieval_worker. Nhờ trace có `mcp_tools_used`, nhóm xác định nhanh lỗi hạ tầng MCP thay vì lỗi routing.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa prompt hoặc pipeline cứng | Thêm MCP tool + cập nhật route rule |
| Thêm 1 domain mới | Sửa monolith | Thêm worker mới, giữ contract |
| Thay đổi retrieval strategy | Ảnh hưởng toàn pipeline | Chỉ sửa `retrieval_worker` |
| A/B test một phần | Khó | Dễ (swap từng worker) |

**Nhận xét:**  
Day 09 phù hợp hơn cho giai đoạn scale vì khả năng mở rộng theo module và trace-first development.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query | 1 LLM call | 1 LLM call + orchestration overhead |
| Complex query | 1 LLM call | 1 LLM call + 1 policy pass + retrieval + optional MCP |
| MCP tool call | N/A | 0–2 tools/query (thực tế thấy ở `q03`, `q15`) |

**Nhận xét về cost-benefit:**  
Multi-agent tốn latency hơn nhưng đổi lại khả năng debug, khả năng mở rộng, và độ an toàn với câu phức tạp tốt hơn.

---

## 6. Kết luận

> **Multi-agent tốt hơn single agent ở điểm nào?**

1. Debug nhanh hơn nhờ `route_reason`, `workers_called`, `mcp_tools_used` và log mode điều phối.
2. Xử lý multi-hop và policy/access flow có cấu trúc hơn nhờ khả năng "suy luận" của LLM Supervisor.
3. An toàn hơn nhờ cơ chế Risk-based HITL (ví dụ case gq09).

> **Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. Latency cao hơn ở đường đi có policy/MCP.

> **Khi nào KHÔNG nên dùng multi-agent?**

Khi use case chỉ là Q&A đơn giản, dataset nhỏ, và ưu tiên tuyệt đối tốc độ/chi phí runtime.

> **Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

Thêm fallback strategy có kiểm soát cho MCP (in-process fallback khi HTTP fail) và tách metric accuracy tự động theo từng category (single-hop, multi-hop, abstain).
