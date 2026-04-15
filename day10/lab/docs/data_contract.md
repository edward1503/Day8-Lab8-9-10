# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `data/raw/policy_export_dirty.csv` (DB/API CSV export) | Batch snapshot, `csv.DictReader` | Duplicate rows, `effective_date` sai format (DD/MM/YYYY), `doc_id` lạ không trong allowlist, `chunk_text` rỗng | `raw_records` vs `cleaned_records` delta; alert nếu `quarantine_records / raw_records > 30%` |
| `data/docs/*.txt` (Policy documents) | File ingest trực tiếp | Version conflict (bản cũ cùng `doc_id`), encoding UTF-8 lỗi, content hash đổi nhưng version metadata không đổi | `embed_upsert count` khớp `cleaned_records`; alert nếu doc mới không xuất hiện trong top-k golden query |
| `hr_leave_policy` export | Batch CSV (trong `policy_export_dirty.csv`) | Version conflict (bản 2025 — 10 ngày vs bản 2026 — 12 ngày cùng tồn tại) | `quarantine_records` filter `stale_hr_policy`; expectation `hr_leave_no_stale_10d_annual` |
| `it_helpdesk_faq` export | Batch CSV | Date format không chuẩn (`01/02/2026` thay vì ISO) | `non_iso_date_count` trước/sau normalize; expectation `effective_date_iso_yyyy_mm_dd` |

**Owner team:** Lab Day 10 Group
**Freshness SLA:** 24h kể từ `exported_at` đến `index_visible` (publish boundary)

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| `chunk_id` | string | Có | Stable key: `sha256(doc_id\|chunk_text\|seq)[:16]` — idempotent upsert khi rerun |
| `doc_id` | string | Có | Phải thuộc `ALLOWED_DOC_IDS` trong `cleaning_rules.py` và `contracts/data_contract.yaml` |
| `chunk_text` | string | Có | Tối thiểu 8 ký tự; không chứa version sai ("14 ngày" refund / "10 ngày phép" HR cũ) |
| `effective_date` | date (YYYY-MM-DD) | Có | Chuẩn hoá từ ISO hoặc DD/MM/YYYY; quarantine nếu không parse được hoặc rỗng |
| `exported_at` | datetime | Có | Dùng tính freshness SLA trong manifest; phải là ISO timestamp |

---

## 3. Quy tắc quarantine vs drop

| Lý do quarantine | Hành động | Ai approve merge lại? |
|-----------------|-----------|----------------------|
| `unknown_doc_id` | Quarantine → `artifacts/quarantine/` | Data owner xác nhận `doc_id` mới trước khi thêm vào allowlist |
| `missing_effective_date` | Quarantine | SME điền ngày hiệu lực vào record gốc |
| `invalid_effective_date_format` | Quarantine | Engineer fix parser hoặc source system |
| `stale_hr_policy_effective_date` | Quarantine (HR cũ < 2026-01-01) | HR xác nhận bản canonical cho 2026 |
| `missing_chunk_text` | Quarantine | Kiểm tra source export — có thể lỗi migration |
| `duplicate_chunk_text` | Quarantine (giữ bản đầu) | Không cần approve — tự dedupe, log để audit |

**Silent drop:** Không áp dụng — mọi record bị loại đều vào quarantine để audit trail.

---

## 4. Phiên bản & canonical

| Document | Canonical source | Version hiện tại | Ghi chú |
|----------|-----------------|-----------------|---------|
| `policy_refund_v4` | `data/docs/policy_refund_v4.txt` | v4 (2026-02-01) | Cửa sổ hoàn tiền = **7 ngày làm việc**; bản v3 (14 ngày) là stale |
| `sla_p1_2026` | `data/docs/sla_p1_2026.txt` | 2026 | SLA P1: phản hồi 15 phút, resolution 4 giờ |
| `hr_leave_policy` | `data/docs/hr_leave_policy.txt` | 2026 (min date = 2026-01-01) | Bản 2025 (10 ngày phép) obsolete; 2026 = **12 ngày phép** dưới 3 năm KN |
| `it_helpdesk_faq` | `data/docs/it_helpdesk_faq.txt` | 2026-02-01 | Khóa TK sau 5 lần sai; đổi MK qua portal mất tối đa 24h đồng bộ |

**Policy versioning cutoff:** `hr_leave_min_effective_date = 2026-01-01` (xem `contracts/data_contract.yaml`)
