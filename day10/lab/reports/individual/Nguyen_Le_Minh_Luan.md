# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Lê Minh Luân 
**ID:** 2A202600398 
**Vai trò:** Monitoring / Docs Owner (Sprint 4)  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** **400–650 từ**

---

## 1. Tôi phụ trách phần nào? (~110 từ)

**File / module:**

- `docs/pipeline_architecture.md` — Kiến trúc đầy đủ: Mermaid flowchart 5 tầng (Sources → Ingest → Clean → Embed → Serving), bảng ranh giới trách nhiệm 7 thành phần, bảng idempotency strategy, liên kết với Day 09 multi-agent, bảng 5 rủi ro đã biết.
- `docs/data_contract.md` — Source map 5 nguồn với failure mode và metric tương ứng; schema cleaned đầy đủ với constraints; bảng quarantine vs fix vs drop; bảng 9 rules + 9 expectations với metric_impact; freshness SLA table; run evidence Sprint 1–3.
- `docs/runbook.md` — 3 incident runbooks đầy đủ 5 bước (Symptom → Detection → Diagnosis → Mitigation → Prevention): incident refund window sai, freshness FAIL, pipeline HALT.

**Kết nối với thành viên khác:**

Tôi tiêu thụ output của mọi sprint trước: log (`artifacts/logs/`), manifest (`artifacts/manifests/`), eval CSV (`artifacts/eval/`), cleaning rules, expectations — để tổng hợp thành tài liệu vận hành. Docs tôi viết là "sổ tay on-call" cho team và cho agent Day 09 phụ thuộc vào data layer này.

**Bằng chứng:** Ba file docs tại `docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md`; tham chiếu run log `run_2026-04-15T08-50Z.log` và eval `eval_clean.csv` / `eval_injected.csv`.

---

## 2. Một quyết định kỹ thuật (~130 từ)

> **Quyết định: Runbook cấu trúc theo incident type, không theo timeline sprint.**

Khi thiết kế `runbook.md`, tôi có hai lựa chọn: (1) viết chronological theo Sprint 1–4, hoặc (2) viết theo **incident type** (refund sai / freshness FAIL / expectation halt).

Tôi chọn cách 2 vì:

1. **Người on-call không biết sprint nào gây ra sự cố** — họ cần tìm theo triệu chứng, không phải ngày chạy.
2. **Timebox rõ ràng**: mỗi incident có khung 0–5' / 5–15' / 15–20' / rollback giúp người mới biết đang ở bước nào.
3. **Prevention không phải blame**: mỗi incident kết thúc bằng action item trên pipeline (thêm expectation, phân tách collection inject vs prod) — đúng nguyên tắc Day 10: "Postmortem phải có action item trên pipeline, không chỉ blame người."

Điều này làm runbook có thể dùng được ngay khi incident xảy ra lúc 2 giờ sáng, không cần đọc toàn bộ lab context.

---

## 3. Một lỗi hoặc anomaly đã xử lý (~130 từ)

> **Anomaly: `data_contract.md` baseline chỉ có 4 nguồn — bỏ sót canonical reference của `it_helpdesk_faq` và `sla_p1_2026`.**

**Triệu chứng:** Template gốc `data_contract.md` liệt kê 4 nguồn trong bảng source map, nhưng `it_helpdesk_faq` và `sla_p1_2026` chỉ được mô tả chung chung, thiếu `failure_mode` cụ thể và `metric/alert` thực sự đo được.

**Phát hiện:** Khi crosscheck với `contracts/data_contract.yaml` (section `canonical_sources`), tôi thấy yaml có đầy đủ `failure_mode` cho cả 4 docs. Template markdown chưa sync.

**Xử lý:** Tôi mở rộng bảng source map thành 5 dòng — tách `data/raw/policy_export_dirty.csv` (batch export) và 4 canonical `.txt` riêng, mỗi nguồn có: failure mode cụ thể, metric đo được (ví dụ `eval_retrieval q_p1_sla contains_expected`), và owner team. Đồng thời thêm bảng "canonical sources" với update frequency và version hiện tại.

**Kết quả:** Data contract doc và YAML đã đồng bộ — team mới đọc doc không cần mở YAML để hiểu nguồn dữ liệu.

---

## 4. Bằng chứng trước / sau (~100 từ)

> **Sprint 3 before/after — dẫn từ `artifacts/eval/`:**

**Before inject (eval_injected.csv):**
```
q_refund_window | contains_expected=yes | hits_forbidden=yes | top1=policy_refund_v4
```
→ Top-1 chunk đúng tài liệu nhưng vẫn tồn tại chunk "14 ngày" trong top-k → agent có thể trả lời sai.

**After clean (eval_clean.csv):**
```
q_refund_window | contains_expected=yes | hits_forbidden=no | top1=policy_refund_v4
q_leave_version | contains_expected=yes | hits_forbidden=no | top1=hr_leave_policy | top1_doc_expected=yes
```
→ Cả 4 golden queries: `contains_expected=yes`, `hits_forbidden=no`. Pipeline fix Rule 6 + prune stale vectors đã loại bỏ hoàn toàn chunk "14 ngày" khỏi index.

**Freshness:** `freshness_check=FAIL` với `age_hours=120.862` — documented trong runbook Incident #2 với mitigation rõ ràng.

---

## 5. Cải tiến tiếp theo (~70 từ)

Nếu có thêm 2 giờ, tôi sẽ:

1. **Freshness 2 boundary (Bonus +1):** Đo tại cả `ingest_boundary` (thời điểm đọc CSV) lẫn `publish_boundary` (sau `embed_upsert`) — ghi cả hai vào manifest để tách biệt "CSV cũ" vs "embed chậm". Hiện tại chỉ đo 1 boundary (`latest_exported_at`).
2. **Auto-check docs sync với YAML:** Script nhỏ so sánh `allowed_doc_ids` trong `data_contract.yaml` vs `ALLOWED_DOC_IDS` trong `cleaning_rules.py` — fail nếu lệch, tránh doc drift theo thời gian.
