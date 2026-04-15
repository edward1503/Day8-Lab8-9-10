# Data Contract — KB Chunk Export

**Nguồn chuẩn:** `contracts/data_contract.yaml`  
**Dataset:** `kb_chunk_export`  
**Owner team:** Lab Day 10 Group  
**Phạm vi contract:** cleaned CSV trước khi embed vào Chroma

## 1. Source map

Sprint 4 yêu cầu ghi tối thiểu nguồn, failure mode và metric. Nguồn ingest trực tiếp là CSV export; các file text trong `data/docs/` đóng vai trò canonical reference để kiểm chứng nội dung đúng phiên bản.

| Nguồn | Vai trò trong pipeline | Failure mode chính | Metric / evidence |
|------|-------------------------|--------------------|-------------------|
| `data/raw/policy_export_dirty.csv` | Input chính của ETL | duplicate, `doc_id` lạ, thiếu `effective_date`, date `DD/MM/YYYY`, HR stale version, refund stale content | `raw_records`, `cleaned_records`, `quarantine_records`, lý do trong quarantine CSV |
| `data/docs/policy_refund_v4.txt` | Canonical policy tham chiếu | export cũ vẫn còn câu `14 ngày làm việc` | expectation `refund_no_stale_14d_window`, eval `q_refund_window` |
| `data/docs/hr_leave_policy.txt` | Canonical HR policy tham chiếu | conflict 2025 `10 ngày` vs 2026 `12 ngày` | quarantine `stale_hr_policy_effective_date`, expectation `hr_leave_no_stale_10d_annual`, eval `q_leave_version` |
| `data/docs/it_helpdesk_faq.txt` | Canonical IT FAQ tham chiếu | date export không ISO hoặc chunk bị lỗi format | expectation `effective_date_iso_yyyy_mm_dd`, cleaned CSV |
| `data/docs/sla_p1_2026.txt` | Canonical SLA tham chiếu | source export thiếu/cũ làm top-1 retrieval lệch | eval `q_p1_sla` |

## 2. Cleaned schema

Schema cleaned đang được code ghi ra bởi `write_cleaned_csv()`:

| Cột | Kiểu | Required | Constraint | Ghi chú |
|-----|------|----------|------------|---------|
| `chunk_id` | string | Có | unique theo cleaned snapshot | Stable ID từ `doc_id`, `chunk_text`, `seq` |
| `doc_id` | string | Có | thuộc allowlist | `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy` |
| `chunk_text` | string | Có | không rỗng, đủ ngữ nghĩa để embed | Có thể được fix/refine bởi cleaning rules |
| `effective_date` | string date | Có | format `YYYY-MM-DD` | Rule 2 chuẩn hoá từ ISO hoặc `DD/MM/YYYY` |
| `exported_at` | string datetime | Không bắt buộc tuyệt đối | nếu có sẽ dùng cho freshness | Lấy từ raw export |

## 3. Field-level contract

### `chunk_id`

- phải ổn định với cùng cleaned content
- được dùng làm khóa `upsert` vào Chroma
- nếu thuật toán đổi, đó là breaking change vì ảnh hưởng idempotency và prune logic

### `doc_id`

- phải thuộc allowlist trong `transform/cleaning_rules.py`
- giá trị ngoài allowlist sẽ bị đưa vào quarantine với reason `unknown_doc_id`
- thêm `doc_id` mới yêu cầu cập nhật đồng thời:
  - allowlist trong code
  - `contracts/data_contract.yaml`
  - tài liệu canonical tương ứng
  - câu hỏi eval nếu nguồn mới quan trọng

### `chunk_text`

- không được rỗng
- không được chứa BOM / zero-width characters
- có thể bị chuẩn hoá whitespace
- riêng `policy_refund_v4` sẽ được sửa `14 ngày làm việc` thành `7 ngày làm việc` nếu không bật `--no-refund-fix`

### `effective_date`

- phải chuẩn hoá về `YYYY-MM-DD`
- nếu là `hr_leave_policy`, ngày phải `>= HR_LEAVE_MIN_EFFECTIVE_DATE`
- nếu lớn hơn `FUTURE_DATE_CUTOFF`, record bị quarantine

### `exported_at`

- giúp tính freshness SLA
- được ghi vào cleaned CSV và manifest dưới dạng `latest_exported_at`
- nếu nguồn không cung cấp timestamp, freshness logic sẽ fallback sang `run_timestamp`

## 4. Cleaning rules gắn với contract

Các rule hiện có bảo vệ contract như sau:

| Rule | Bảo vệ field nào | Hành động |
|------|------------------|-----------|
| Allowlist doc id | `doc_id` | quarantine record lạ |
| Normalize effective date | `effective_date` | parse hoặc quarantine |
| HR stale cutoff | `effective_date`, `doc_id` | loại bản HR cũ |
| Empty chunk check | `chunk_text` | quarantine |
| Dedup by normalized text | `chunk_text` | giữ snapshot sạch, không lặp |
| Refund fix 14 -> 7 | `chunk_text` | sửa business content stale |
| Invisible char detection | `chunk_text` | quarantine lỗi encoding |
| Future date cutoff | `effective_date` | quarantine dữ liệu bất thường |
| Whitespace normalization | `chunk_text` | fix format trước khi sinh `chunk_id` |

## 5. Expectations gắn với contract

Expectation suite đóng vai trò "consumer-side contract check" trước khi publish:

| Expectation | Severity | Contract được kiểm |
|-------------|----------|--------------------|
| `min_one_row` | halt | dataset không được rỗng |
| `no_empty_doc_id` | halt | `doc_id` phải có |
| `refund_no_stale_14d_window` | halt | refund content phải đúng version |
| `chunk_min_length_8` | warn | `chunk_text` không quá ngắn |
| `effective_date_iso_yyyy_mm_dd` | halt | `effective_date` đúng format |
| `hr_leave_no_stale_10d_annual` | halt | HR content đúng phiên bản hiện hành |
| `no_bom_or_invisible_char_in_cleaned` | halt | text không có lỗi encoding |
| `no_future_effective_date_beyond_cutoff` | warn | ngày hiệu lực không quá xa |
| `chunk_text_min_word_count` | warn | chunk đủ ngữ nghĩa để embed |

## 6. Quarantine contract

Record vi phạm contract không được silent drop. Chúng phải đi vào `artifacts/quarantine/quarantine_<run-id>.csv`.

Các reason đã thấy trên sample data:

| Reason | Ý nghĩa |
|--------|---------|
| `duplicate_chunk_text` | trùng nội dung sau normalize |
| `missing_effective_date` | thiếu ngày hiệu lực |
| `stale_hr_policy_effective_date` | bản HR cũ hơn cutoff |
| `unknown_doc_id` | nguồn ngoài catalog được chấp thuận |

Từ góc nhìn consumer, quarantine CSV là bằng chứng để giải thích vì sao `raw_records != cleaned_records`.

## 7. Freshness contract

| Mục | Giá trị mặc định | Nguồn |
|-----|------------------|------|
| SLA | 24 giờ | `FRESHNESS_SLA_HOURS` |
| Boundary | `latest_exported_at` | manifest |
| Fallback khi thiếu export timestamp | `run_timestamp` | manifest |

Điểm quan trọng: theo code hiện tại, `WARN` không có nghĩa là dữ liệu quá cũ; `WARN` chỉ xuất hiện khi timestamp trong manifest thiếu hoặc parse lỗi. Nếu timestamp hợp lệ nhưng quá hạn SLA, kết quả là `FAIL`.

## 8. Config qua environment variables

Contract hiện phụ thuộc vào các biến môi trường sau:

| Env var | Default | Tác động |
|---------|---------|----------|
| `HR_LEAVE_MIN_EFFECTIVE_DATE` | `2026-01-01` | cutoff loại bản HR cũ |
| `FUTURE_DATE_CUTOFF` | `2030-01-01` | cutoff cho future-dated policy |
| `CHUNK_MIN_WORD_COUNT` | `5` | ngưỡng expectation E9 |
| `FRESHNESS_SLA_HOURS` | `24` | SLA freshness |
| `CHROMA_COLLECTION` | `day10_kb` | collection publish |
| `CHROMA_DB_PATH` | `./chroma_db` | nơi lưu vector DB |

## 9. Sample evidence từ artifact hiện có

Từ raw sample 10 dòng:

| Giai đoạn | Số dòng |
|----------|---------|
| Raw | 10 |
| Cleaned | 6 |
| Quarantine | 4 |

Hai bằng chứng quan trọng:

1. `artifacts/cleaned/cleaned_2026-04-15T08-50Z.csv` chỉ còn refund text đúng `7 ngày làm việc`
2. `artifacts/eval/eval_clean.csv` cho `q_refund_window` là `contains_expected=yes` và `hits_forbidden=no`

## 10. Change management

Những thay đổi sau phải được xem là thay đổi contract và cần cập nhật docs + YAML:

1. thêm hoặc bỏ một `doc_id`
2. đổi tên cột cleaned CSV
3. đổi logic sinh `chunk_id`
4. đổi boundary freshness
5. đổi severity của một expectation `halt`
