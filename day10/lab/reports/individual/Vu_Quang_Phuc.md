# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Vũ Quang Phúc  
**Vai trò:** Sprint 4 Documentation & Reporting Completion  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** **400–650 từ**

---

## 1. Tôi phụ trách phần nào?

Trong Sprint 4, tôi tập trung vào phần hoàn thiện tài liệu vận hành và báo cáo cuối cùng của repo. Cụ thể, tôi hoàn chỉnh ba file `docs/pipeline_architecture.md`, `docs/data_contract.md`, và `docs/runbook.md` dựa trên chính code đang có trong `etl_pipeline.py`, `transform/cleaning_rules.py`, `quality/expectations.py`, `monitoring/freshness_check.py`, cùng các artifact thật như `artifacts/manifests/manifest_2026-04-15T08-50Z.json`, `artifacts/cleaned/cleaned_2026-04-15T08-50Z.csv`, `artifacts/quarantine/quarantine_2026-04-15T08-50Z.csv`, `artifacts/eval/eval_clean.csv`, và `artifacts/eval/eval_injected.csv`.

Tôi cũng hoàn thiện `reports/group_report.md` để tổng hợp lại toàn bộ kết quả các sprint trước thành bản nộp thống nhất. Công việc của tôi phụ thuộc trực tiếp vào output từ các thành viên khác: pipeline baseline của Minh Hoàng, tầng cleaning/expectation của Anh Quân, và evidence eval của Đôn Đức. Vai trò của tôi là biến những output đó thành tài liệu mà người khác có thể đọc, vận hành, và đối chiếu với artifact thật mà không phải đoán.

---

## 2. Một quyết định kỹ thuật

Quyết định kỹ thuật quan trọng nhất của tôi là viết lại phần docs theo **hành vi thật của code**, không theo mô tả “có thể đúng” trên template. Điểm rõ nhất là freshness. Nếu chỉ nhìn mô tả chung, rất dễ viết `WARN` như một mức “hơi cũ”, nhưng khi đối chiếu `monitoring/freshness_check.py` tôi thấy code hiện tại chỉ trả:

- `PASS` khi timestamp hợp lệ và còn trong SLA
- `FAIL` khi timestamp hợp lệ nhưng quá hạn SLA
- `WARN` khi timestamp trong manifest thiếu hoặc parse lỗi

Tôi giữ đúng semantics này trong `docs/runbook.md` và `docs/data_contract.md`. Tôi chọn cách làm này vì tài liệu vận hành chỉ có giá trị khi nó khớp chính xác với cách hệ thống phản ứng. Nếu docs nói một kiểu còn script chạy kiểu khác, người on-call sẽ triage sai hướng. Với bài lab này, việc giải thích đúng “boundary freshness đo từ `latest_exported_at`, không phải `run_timestamp`” quan trọng hơn viết tài liệu dài nhưng mơ hồ.

---

## 3. Một lỗi hoặc anomaly đã xử lý

Anomaly tôi xử lý không nằm ở code pipeline mà ở **độ lệch giữa tài liệu và implementation thực tế**. Khi rà soát Sprint 4, tôi thấy các file docs cũ có nhiều chỗ mô tả rộng hơn thực tế, trong khi report nhóm còn để nguyên template trắng. Nếu nộp như vậy thì phần tài liệu sẽ rất dễ mâu thuẫn với artifact, nhất là ở phần freshness, quarantine reasons, và publish boundary.

Tôi xử lý bằng cách đọc lại raw sample và artifact thật. Ví dụ, từ `quarantine_2026-04-15T08-50Z.csv` tôi xác nhận bốn lý do hiện đang xuất hiện thật là `duplicate_chunk_text`, `missing_effective_date`, `stale_hr_policy_effective_date`, và `unknown_doc_id`. Từ `cleaned_2026-04-15T08-50Z.csv` tôi xác nhận row refund đã được sửa về `7 ngày làm việc`, còn date `01/02/2026` đã được chuẩn hoá thành `2026-02-01`. Từ manifest và lệnh `python3 etl_pipeline.py freshness --manifest .../manifest_2026-04-15T08-50Z.json`, tôi xác nhận sample hiện trả `FAIL` vì source export cũ hơn SLA 24 giờ. Sau đó tôi cập nhật lại docs và group report để toàn bộ narrative khớp với evidence này.

---

## 4. Bằng chứng trước / sau

Tôi dùng hai file eval để viết phần before/after trong report:

- `artifacts/eval/eval_injected.csv`: `q_refund_window` có `contains_expected=yes` nhưng `hits_forbidden=yes`
- `artifacts/eval/eval_clean.csv`: `q_refund_window` có `contains_expected=yes` và `hits_forbidden=no`

Điểm này rất đáng giá vì nó cho thấy pipeline clean không chỉ giữ top-1 “có vẻ đúng”, mà còn dọn được chunk stale khỏi top-k. Tôi cũng dùng `q_leave_version` trong `eval_clean.csv` làm bằng chứng bổ sung: `top1_doc_expected=yes`, nghĩa là collection đã ưu tiên đúng policy HR 2026 thay vì bản 2025.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ làm một script kiểm tra đồng bộ tài liệu với implementation: so sánh `allowed_doc_ids` trong code với YAML contract, kiểm tra các expectation có được mô tả trong docs hay không, và cảnh báo khi report đang tham chiếu artifact không tồn tại. Việc này sẽ giúp Sprint 4 bền hơn khi nhóm tiếp tục chỉnh code sau này.
