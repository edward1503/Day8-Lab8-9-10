# Data Contract — Lab Day 10: KB Chunk Export

> Đồng bộ với `contracts/data_contract.yaml` (version 1.1, last_updated: 2026-04-15).  
> **Owner team:** Lab Day 10 Group  
> **Freshness SLA:** 24h kể từ `exported_at` đến `index_visible` (publish boundary)

---

## 1. Nguồn dữ liệu (Source Map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / Alert |
|-------|-------------------|-------------------|----------------|
| `data/raw/policy_export_dirty.csv` (DB/API CSV export) | Batch snapshot, `csv.DictReader`, UTF-8 | (1) Duplicate rows — `duplicate_chunk_text`; (2) `effective_date` sai format `DD/MM/YYYY`; (3) `doc_id` lạ không trong allowlist; (4) `chunk_text` rỗng; (5) BOM/invisible char | `raw_records` vs `cleaned_records` delta; **alert nếu `quarantine_records / raw_records > 30%`**; expectation E3/E5/E6 halt |
| `data/docs/policy_refund_v4.txt` | Canonical reference — không ingest trực tiếp vào CSV pipeline; dùng để verify nội dung chunk | Version conflict (bản v3 chứa "14 ngày" vs v4 chứa "7 ngày" cùng tồn tại trong export) | Rule 6 fix + expectation E3 halt; `eval_retrieval q_refund_window hits_forbidden` |
| `data/docs/hr_leave_policy.txt` | Canonical reference (bản 2026 — 12 ngày phép) | Version conflict 2025 (10 ngày) vs 2026 (12 ngày) cùng tồn tại trong batch export | Rule 3 quarantine `stale_hr_policy_effective_date`; expectation E6 halt; `eval_retrieval q_leave_version top1_doc_expected` |
| `data/docs/it_helpdesk_faq.txt` | Canonical reference | Date format không chuẩn (`01/02/2026` thay vì ISO) trong export | Rule 2 normalize + E5 halt; `non_iso_date_count` trước/sau normalize |
| `data/docs/sla_p1_2026.txt` | Canonical reference | SLA thay đổi khi hợp đồng mới mà export chưa cập nhật | `embed_upsert count` khớp `cleaned_records`; golden query `q_p1_sla contains_expected` |

**Tất cả nguồn canonical:**

| Document | Owner | Update frequency | Version hiện tại | Ghi chú |
|----------|-------|-----------------|-----------------|---------|
| `policy_refund_v4` | CS Policy Team | Per policy revision | v4 (2026-02-01) | Refund window = **7 ngày làm việc**; bản v3 (14 ngày) là stale — Rule 6 fix |
| `sla_p1_2026` | IT Operations | Annual | 2026 | SLA P1: phản hồi **15 phút**, resolution **4 giờ** |
| `hr_leave_policy` | HR Department | Annual (đầu năm) | 2026 (min date 2026-01-01) | Bản 2025 (10 ngày) obsolete; 2026 = **12 ngày phép** dưới 3 năm KN |
| `it_helpdesk_faq` | IT Helpdesk | Quarterly | 2026-02-01 | Khóa TK sau **5 lần** sai; đổi MK qua portal mất tối đa 24h đồng bộ |

---

## 2. Schema Cleaned

| Cột | Kiểu | Bắt buộc | Constraints | Ghi chú |
|-----|------|----------|-------------|---------|
| `chunk_id` | string | **Có** | Unique, stable key | `sha256(doc_id\|chunk_text\|seq)[:16]` → `{doc_id}_{seq}_{hash}`; idempotent upsert khi rerun |
| `doc_id` | string | **Có** | `enum: [policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy]` | Phải thuộc `ALLOWED_DOC_IDS`; Rule 1 quarantine nếu sai |
| `chunk_text` | string | **Có** | `min_length: 8`, `min_word_count: 5`, `no_bom: true` | Không chứa version sai; whitespace đã normalize (Rule 9); BOM đã quarantine (Rule 7) |
| `effective_date` | date | **Có** | Format `YYYY-MM-DD`; min `2026-01-01` (HR); max `2030-01-01` (env `FUTURE_DATE_CUTOFF`) | Chuẩn hoá từ ISO hoặc DD/MM/YYYY; quarantine nếu không parse được hoặc rỗng |
| `exported_at` | datetime | Không (có thì tốt) | ISO datetime | Dùng tính freshness SLA trong manifest; nếu thiếu → freshness WARN |

**Breaking changes cần alert:**
- Đổi tên cột (vd `doc_id` → `document_id`) → Rule 1 + E2 halt toàn bộ pipeline
- Xóa cột `effective_date` → E5 halt
- Thêm cột mới → không breaking (CSV DictReader tolerant), nhưng phải đồng bộ `contracts/data_contract.yaml`

---

## 3. Quy tắc Quarantine vs Drop vs Fix

| Reason | Hành động | File output | Ai approve merge lại? |
|--------|-----------|-------------|----------------------|
| `unknown_doc_id` | **Quarantine** → `artifacts/quarantine/` | `quarantine_<run_id>.csv` | Data owner xác nhận `doc_id` mới → thêm vào `ALLOWED_DOC_IDS` và `allowed_doc_ids` YAML |
| `missing_effective_date` | **Quarantine** | `quarantine_<run_id>.csv` | SME điền ngày hiệu lực vào record gốc ở hệ nguồn |
| `invalid_effective_date_format` | **Quarantine** | `quarantine_<run_id>.csv` | Engineer fix parser hoặc source system export format |
| `stale_hr_policy_effective_date` | **Quarantine** (HR < `HR_LEAVE_MIN_EFFECTIVE_DATE`) | `quarantine_<run_id>.csv` | HR xác nhận bản canonical 2026 — không merge bản cũ |
| `missing_chunk_text` | **Quarantine** | `quarantine_<run_id>.csv` | Kiểm tra source export — có thể lỗi migration; re-export nếu cần |
| `duplicate_chunk_text` | **Quarantine** (giữ bản đầu tiên) | `quarantine_<run_id>.csv` | Không cần approve — tự dedupe; log để audit trail |
| `bom_or_invisible_char_in_text` | **Quarantine** | `quarantine_<run_id>.csv` | Engineer fix encoding pipeline nguồn (không phải strip tại đây — xử lý gốc rễ) |
| `effective_date_beyond_future_cutoff` | **Quarantine** | `quarantine_<run_id>.csv` | Xác nhận ngày hợp lệ; hoặc tăng `FUTURE_DATE_CUTOFF` nếu policy thật có ngày tương lai xa |
| stale refund window | **Fix in-place** — "14 ngày" → "7 ngày" + marker `[cleaned: stale_refund_window]` | `cleaned_<run_id>.csv` | Auto-fix; record vẫn vào cleaned — expectation E3 verify sau fix |
| whitespace thừa | **Fix in-place** — normalize + marker `[cleaned: whitespace_normalized]` | `cleaned_<run_id>.csv` | Auto-fix; không cần approve |

**Nguyên tắc:** Không silent drop — mọi record bị loại đều phải có lý do ghi vào quarantine CSV.

---

## 4. Quality Rules & Expectations

### Cleaning Rules

| ID | Mô tả ngắn | Severity | Env var / Flag |
|----|-----------|----------|----------------|
| Rule 1 | Allowlist `doc_id` | quarantine | — |
| Rule 2 | Normalize `effective_date` (ISO / DD/MM/YYYY) | quarantine | — |
| Rule 3 | HR stale version cutoff | quarantine | `HR_LEAVE_MIN_EFFECTIVE_DATE` (default 2026-01-01) |
| Rule 4 | Empty `chunk_text` | quarantine | — |
| Rule 5 | Deduplicate `chunk_text` | quarantine | — |
| Rule 6 | Fix stale refund window 14→7 ngày | fix | `--no-refund-fix` flag |
| Rule 7 | BOM / invisible char detection | quarantine | — |
| Rule 8 | Future date cutoff | quarantine | `FUTURE_DATE_CUTOFF` (default 2030-01-01) |
| Rule 9 | Whitespace normalization | fix | — |

### Expectations

| ID | Name | Severity | metric_impact |
|----|------|----------|---------------|
| E1 | `min_one_row` | **halt** | Pipeline rỗng → halt toàn bộ embed |
| E2 | `no_empty_doc_id` | **halt** | Header mất cột → toàn bộ doc_id rỗng → halt |
| E3 | `refund_no_stale_14d_window` | **halt** | Bypass Rule 6 → E3 FAIL → không embed chunk sai |
| E4 | `chunk_min_length_8` | warn | Chunking hỏng → short chunks → warn để review |
| E5 | `effective_date_iso_yyyy_mm_dd` | **halt** | Rule 2 bị bypass → non-ISO date lọt → halt |
| E6 | `hr_leave_no_stale_10d_annual` | **halt** | Rule 3 bị bypass → bản HR 2025 lọt → halt |
| E7 | `no_bom_or_invisible_char_in_cleaned` | **halt** | Lưới an toàn thứ 2 sau Rule 7; bypass Rule 7 + inject BOM → E7 halt |
| E8 | `no_future_effective_date_beyond_cutoff` | warn | bypass Rule 8 + inject 2099 → E8 WARN |
| E9 | `chunk_text_min_word_count` | warn | Inject chunk < 5 từ → E9 WARN; min override qua `CHUNK_MIN_WORD_COUNT` |

---

## 5. Freshness SLA

| Tham số | Giá trị | Ghi chú |
|---------|---------|---------|
| **Boundary đo** | `publish` (sau `embed_upsert`) | Không đo ở `cron_start` — tránh "pipeline green nhưng user thấy cũ" |
| **SLA** | 24 giờ | Kể từ `exported_at` đến thời điểm index visible |
| **PASS** | `age_hours ≤ 24` | Data tươi — agent có thể serve |
| **WARN** | Không có `exported_at` trong manifest | Cần điều tra nguồn export |
| **FAIL** | `age_hours > 24` | Cần re-export và re-run pipeline |
| **Alert channel** | Console log (`freshness_check=FAIL {detail}`) | Override `FRESHNESS_SLA_HOURS` trong `.env` |

**Lưu ý CSV mẫu:** `exported_at = 2026-04-10` → `age_hours ≈ 120h` → `freshness_check=FAIL` là **có chủ đích** để demo SLA breach. Để test PASS: set `FRESHNESS_SLA_HOURS=200` trong `.env`.

---

## 6. Versioning & Canonical

**Policy versioning cutoff (tất cả đọc từ env — không hard-code):**

```
HR_LEAVE_MIN_EFFECTIVE_DATE = 2026-01-01   # Rule 3 cutoff
FUTURE_DATE_CUTOFF           = 2030-01-01   # Rule 8 cutoff
CHUNK_MIN_WORD_COUNT         = 5            # E9 threshold
FRESHNESS_SLA_HOURS          = 24           # freshness SLA
```

**Distinction (d):** Thay `HR_LEAVE_MIN_EFFECTIVE_DATE=2025-01-01` trong `.env` → bản HR 2025 (10 ngày) KHÔNG bị quarantine → quyết định clean thay đổi mà không cần sửa code.

---

## 7. Run Evidence (Sprint 1–3)

| Run ID | raw | cleaned | quarantine | freshness | Ghi chú |
|--------|-----|---------|-----------|-----------|---------|
| `sprint1` | 10 | 6 | 4 | FAIL (120h) | Baseline — 6 rules |
| `sprint2` | 10 | 6 | 4 | FAIL | Sprint 2 — 9 rules + 9 expectations |
| `inject-bad` | 10 | 6 | 4 | FAIL | `--no-refund-fix --skip-validate`; `hits_forbidden=yes` cho `q_refund_window` |
| `clean-baseline` | 10 | 6 | 4 | FAIL | Pipeline chuẩn sau inject; `hits_forbidden=no` |
| `2026-04-15T08-50Z` | 10 | 6 | 4 | FAIL | Run mới nhất; `embed_upsert count=6` |
