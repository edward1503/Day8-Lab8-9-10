# Quality report — Lab Day 10 (nhóm)

**run_id:** `inject-bad` (Scenario: Corruption Inject) vs `clean-baseline` (Scenario: Clean Pipeline)  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (Inject-bad) | Sau (Clean-baseline) | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 10 | 10 | Nguồn CSV mẫu |
| cleaned_records | 6 | 6 | Số lượng record không đổi |
| quarantine_records | 4 | 4 | Chủ yếu do doc_id lạ và text rỗng |
| Expectation halt? | **YES** | NO | Inject-bad fail rule E3 |

---

## 2. Before / after retrieval (bắt buộc)

Dẫn link tới: [eval_clean.csv](file:///d:/VSCODE/VINAI/Day8-Lab8-9-10/day10/lab/artifacts/eval/eval_clean.csv) và [eval_injected.csv](file:///d:/VSCODE/VINAI/Day8-Lab8-9-10/day10/lab/artifacts/eval/eval_injected.csv)

**Câu hỏi then chốt:** refund window (`q_refund_window`)  

*   **Trước (Khi bị inject lỗi):**
    *   `top1_preview`: "Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng." (Tuy nhiên có chunk 14 ngày tồn tại trong top-k)
    *   `hits_forbidden`: **yes** ❌ (Phát hiện thấy chunk chứa "14 ngày làm việc")
*   **Sau (Khi đã chạy Clean Pipeline):**
    *   `top1_preview`: "Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng."
    *   `hits_forbidden`: **no** ✅ (Toàn bộ top-k đã được fix 14 -> 7)

**Merit (khuyến nghị):** versioning HR — `q_leave_version`

*   **Cả 2 run:** `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`.
*   **Nhận xét:** Rule 3 (HR cutoff) hoạt động ổn định trong cả 2 trường hợp vì không bị tắt bởi flag `--no-refund-fix`.

---

## 3. Freshness & monitor

*   **Kết quả:** **FAIL**
*   **Chi tiết:** `age_hours: ~121h`, `sla_hours: 24h`
*   **Giải thích:** Do bộ dữ liệu mẫu (CSV) có trường `exported_at` cố định từ ngày 2026-04-10, vượt quá SLA 24 giờ. Trong môi trường production, điều này sẽ kích hoạt cảnh báo tới Ingestion Team.

---

## 4. Corruption inject (Sprint 3)

**Kịch bản làm hỏng:**
Sử dụng flag `--no-refund-fix` để ngăn chặn Rule 6 (sửa 14 ngày thành 7 ngày) và flag `--skip-validate` để ép pipeline nạp dữ liệu "bẩn" này vào Vector DB bất chấp việc Expectation `E3` bị Fail.

**Cách phát hiện:**
1.  **Hệ thống:** Expectation `refund_no_stale_14d_window` báo **FAIL** ngay trong log pipeline.
2.  **Retrieval:** Script `eval_retrieval.py` phát hiện từ khóa cấm ("14 ngày") trong kết quả tìm kiếm, đánh dấu cột `hits_forbidden=yes`.

---

## 5. Hạn chế & việc chưa làm

- Hiện tại freshness check chỉ dựa trên manifest, chưa tích hợp Slack/Email alert.
- Rule khử trùng (deduplication) mới chỉ dựa trên nội dung text, chưa tính đến việc map semantic similarity để gộp các chunk gần giống nhau.
