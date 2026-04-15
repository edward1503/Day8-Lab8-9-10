# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Duy Minh Hoàng  
**Vai trò:** Ingestion / Cleaning / Embed Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** **400–650 từ**

---

## 1. Tôi phụ trách phần nào? (~110 từ)

**File / module:**

- `etl_pipeline.py` — Entrypoint chính: luồng ingest → clean → validate → embed → manifest → freshness check.
- `transform/cleaning_rules.py` — 6 baseline cleaning rules: allowlist `doc_id`, chuẩn hoá `effective_date` (ISO + DD/MM/YYYY), quarantine HR stale (< 2026-01-01), quarantine `chunk_text` rỗng, dedupe theo `_norm_text`, fix refund window 14→7 ngày.
- `quality/expectations.py` — 6 baseline expectations kiểm tra dữ liệu sau clean.
- `contracts/data_contract.yaml` — Điền `owner_team`, `alert_channel`, đồng bộ schema và `allowed_doc_ids`.
- `docs/data_contract.md` — Source map đầy đủ 4 nguồn với failure mode và metric tương ứng.

**Kết nối với thành viên khác:**

Tôi chịu trách nhiệm toàn bộ luồng pipeline từ ingestion đến embed, đảm bảo output `cleaned_*.csv` và `quarantine_*.csv` đúng schema để các sprint sau (inject corruption, eval retrieval) có baseline ổn định.

**Bằng chứng:** Run log tại `artifacts/logs/run_2026-04-15T08-50Z.log`, manifest tại `artifacts/manifests/manifest_2026-04-15T08-50Z.json`.

---

## 2. Một quyết định kỹ thuật (~130 từ)

> **Quyết định: Stable `chunk_id` = hash-based key thay vì UUID ngẫu nhiên.**

Khi thiết kế idempotency cho embed, tôi sử dụng `_stable_chunk_id()` với công thức `sha256(doc_id|chunk_text|seq)[:16]` tạo ra ID dạng `{doc_id}_{seq}_{hash}`. Lý do:

1. **Idempotent upsert:** Chạy pipeline 2 lần trên cùng dữ liệu → cùng `chunk_id` → Chroma upsert ghi đè, không phình collection.
2. **Prune stale vectors:** Sau mỗi run, pipeline so sánh `prev_ids` trong collection với `ids` mới, xoá ID không còn tồn tại. Điều này đảm bảo vector store luôn phản chiếu đúng snapshot cleaned hiện tại (publish boundary).
3. **Traceability:** `chunk_id` chứa `doc_id` và `seq` giúp debug nhanh — nhìn ID biết ngay chunk thuộc tài liệu nào.

Nếu dùng `uuid4()`, mỗi lần rerun sẽ tạo ID mới → duplicate vector → retrieval bị nhiễu bởi chunk trùng nội dung.

---

## 3. Một lỗi hoặc anomaly đã xử lý (~130 từ)

> **Anomaly: Row 5 trong CSV — `chunk_text` rỗng + `effective_date` rỗng.**

**Triệu chứng:** Row 5 (`chunk_id=5, doc_id=policy_refund_v4`) có cả hai trường `chunk_text` và `effective_date` đều trống. Đây là lỗi export từ source system (có thể migration failure).

**Phát hiện:** Cleaning rule kiểm tra `effective_date` trước (rule #2) → `_normalize_effective_date("")` trả về `("", "empty_effective_date")` → record bị quarantine ngay với reason `missing_effective_date`, không cần đến rule #4 (chunk_text rỗng).

**Xử lý:** Record được đưa vào `artifacts/quarantine/quarantine_2026-04-15T08-50Z.csv` thay vì silent drop — đảm bảo audit trail. Log ghi rõ `quarantine_records=4` (bao gồm row này).

**Metric:** `raw_records=10` → `cleaned_records=6`, `quarantine_records=4`. Không có dữ liệu nào bị mất mà không có lý do ghi nhận.

---

## 4. Bằng chứng trước / sau (~100 từ)

> **`run_id=2026-04-15T08-50Z`** — Kết quả pipeline Sprint 1:

```
run_id=2026-04-15T08-50Z
raw_records=10
cleaned_records=6
quarantine_records=4
```

**Expectations — tất cả OK:**
```
expectation[min_one_row] OK (halt) :: cleaned_rows=6
expectation[no_empty_doc_id] OK (halt) :: empty_doc_id_count=0
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
expectation[chunk_min_length_8] OK (warn) :: short_chunks=0
expectation[effective_date_iso_yyyy_mm_dd] OK (halt) :: non_iso_rows=0
expectation[hr_leave_no_stale_10d_annual] OK (halt) :: violations=0
```

**Embed:** `embed_upsert count=6 collection=day10_kb` — 6 vectors upsert thành công.

**Freshness:** `freshness_check=FAIL` với `age_hours=120.862` (>24h SLA) — đúng kỳ vọng vì CSV mẫu có `exported_at=2026-04-10`.

---

## 5. Cải tiến tiếp theo (~70 từ)

Anh Quân đã mở rộng tầng cleaning với 3 rules mới (BOM, future date, whitespace) và 3 expectations (E7–E9), đồng thời đề xuất pydantic validate. Minh Luân đã hoàn thiện docs/runbook và đề xuất freshness 2 boundary + auto-check docs sync. Dựa trên đó, nếu có thêm 2 giờ, tôi sẽ tập trung vào phần pipeline/embed mình phụ trách:

1. **Blue/green embed với staging collection:** Thay vì upsert trực tiếp lên `day10_kb` (production), tôi sẽ embed vào collection staging `day10_kb_staging`, chạy eval retrieval trên staging trước, nếu pass thì swap alias — đảm bảo zero-downtime và rollback tức thì khi data lỗi, đúng pattern slide Day 10 (staging → swap alias).
2. **Parallel embed + validation gate:** Tích hợp kết quả eval retrieval (4 golden queries) thành một quality gate tự động ngay sau embed — nếu `hits_forbidden=yes` trên bất kỳ câu nào thì pipeline tự rollback về collection cũ, không cần chờ on-call đọc runbook.
