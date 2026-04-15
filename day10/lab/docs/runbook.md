# Runbook — Day 10 Data Pipeline

**Owner:** Monitoring / Docs Owner  
**Entrypoint chính:** `etl_pipeline.py`  
**Mục tiêu:** chạy pipeline, kiểm tra freshness, và xử lý nhanh các lỗi dữ liệu phổ biến

## 1. Lệnh chuẩn

Chạy toàn bộ pipeline:

```bash
python etl_pipeline.py run
```

Chạy với run id rõ ràng:

```bash
python etl_pipeline.py run --run-id sprint4-docs
```

Kiểm tra freshness của một manifest:

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

Đánh giá retrieval sau khi đã embed:

```bash
python eval_retrieval.py --out artifacts/eval/eval_clean.csv
```

## 2. Trình tự vận hành chuẩn

1. Chạy `python etl_pipeline.py run`
2. Ghi lại `run_id`
3. Mở manifest tương ứng trong `artifacts/manifests/`
4. Kiểm tra `raw_records`, `cleaned_records`, `quarantine_records`
5. Chạy `python etl_pipeline.py freshness --manifest ...`
6. Chạy `python eval_retrieval.py --out ...`
7. Nếu có inject demo ở Sprint 3, luôn chạy lại một run chuẩn để publish snapshot sạch

## 3. Kết quả mong đợi của một run tốt

Với sample data hiện tại:

| Metric | Giá trị mong đợi |
|-------|-------------------|
| `raw_records` | 10 |
| `cleaned_records` | 6 |
| `quarantine_records` | 4 |
| refund text | chỉ còn `7 ngày làm việc` |
| `q_refund_window` trong eval sạch | `contains_expected=yes`, `hits_forbidden=no` |
| `q_leave_version` | `top1_doc_expected=yes` |

Lưu ý: sample data cố ý có `exported_at` cũ, nên freshness có thể FAIL dù pipeline vẫn chạy thành công.

## 4. PASS / WARN / FAIL của freshness

Theo code trong `monitoring/freshness_check.py`, logic là:

1. đọc `latest_exported_at` từ manifest
2. nếu thiếu thì fallback sang `run_timestamp`
3. so với `now` theo `FRESHNESS_SLA_HOURS`

Ý nghĩa trạng thái:

| Trạng thái | Điều kiện thực tế trong code | Hành động |
|-----------|-------------------------------|-----------|
| `PASS` | timestamp hợp lệ và `age_hours <= sla_hours` | tiếp tục dùng snapshot |
| `FAIL` | timestamp hợp lệ nhưng `age_hours > sla_hours` | re-export data hoặc nới SLA cho lab |
| `WARN` | không parse được cả `latest_exported_at` lẫn `run_timestamp` | sửa manifest / source timestamp |

Với manifest sample hiện có, `latest_exported_at` là `2026-04-10T08:00:00`, nên nếu SLA là 24 giờ thì kết quả đúng là `FAIL`.

## 5. Checklist khi pipeline lỗi

Nếu `python etl_pipeline.py run` không ra `PIPELINE_OK`, kiểm tra theo thứ tự:

1. raw file có tồn tại không
2. cleaned và quarantine CSV có được ghi ra không
3. expectation nào fail
4. có dùng `--no-refund-fix` hoặc `--skip-validate` không
5. embed có lỗi dependency / Chroma không
6. manifest có được ghi không

## 6. Incident 1 — Refund answer sai `14 ngày`

### Dấu hiệu

- người dùng hoặc eval vẫn thấy `14 ngày làm việc`
- `artifacts/eval/*.csv` có `hits_forbidden=yes` cho `q_refund_window`

### Cách kiểm tra

```bash
python eval_retrieval.py --out artifacts/eval/check_refund.csv
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

Mở thêm:

- `artifacts/cleaned/cleaned_<run-id>.csv`
- `artifacts/manifests/manifest_<run-id>.json`

### Root cause thường gặp

1. run inject được chạy với `--no-refund-fix --skip-validate`
2. chưa rerun pipeline chuẩn sau inject
3. snapshot cũ còn trong collection trước khi run sạch mới hoàn tất

### Cách xử lý

```bash
python etl_pipeline.py run --run-id refund-fix
python eval_retrieval.py --out artifacts/eval/eval_after_refund_fix.csv
```

Kỳ vọng sau fix:

- cleaned CSV không còn chuỗi `14 ngày làm việc`
- eval `q_refund_window` có `hits_forbidden=no`

## 7. Incident 2 — Freshness FAIL

### Dấu hiệu

`python etl_pipeline.py freshness --manifest ...` trả `FAIL {...}`

### Cách diễn giải

Nếu manifest có:

- `run_timestamp` mới
- nhưng `latest_exported_at` cũ

thì pipeline vừa xử lý **một snapshot nguồn đã cũ**. Vấn đề nằm ở source/export, không phải ở bước embed.

### Cách xử lý

Trong lab có 2 cách:

1. re-export dữ liệu với `exported_at` mới hơn rồi chạy lại pipeline
2. nới `FRESHNESS_SLA_HOURS` trong `.env` để demo PASS trên sample data

Ví dụ:

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_2026-04-15T08-50Z.json
```

### Khi nào nên dùng cách 2

Chỉ dùng cho lab/demo. Với production thinking, freshness FAIL là tín hiệu cần refresh source data.

## 8. Incident 3 — PIPELINE_HALT

### Dấu hiệu

Pipeline dừng với exit code `2` và log có `PIPELINE_HALT`.

### Các nguyên nhân hay gặp

| Expectation fail | Ý nghĩa |
|------------------|---------|
| `min_one_row` | tất cả record bị quarantine hoặc raw rỗng |
| `no_empty_doc_id` | parser/header có vấn đề |
| `refund_no_stale_14d_window` | refund stale content lọt qua clean |
| `effective_date_iso_yyyy_mm_dd` | date normalization không đủ |
| `hr_leave_no_stale_10d_annual` | bản HR cũ còn trong cleaned |
| `no_bom_or_invisible_char_in_cleaned` | lỗi encoding chưa bị chặn |

### Cách xử lý

1. Mở `artifacts/quarantine/quarantine_<run-id>.csv`
2. Mở `artifacts/cleaned/cleaned_<run-id>.csv`
3. Xác định expectation fail nào
4. Chỉ dùng `--skip-validate` khi demo inject, không dùng cho run publish thật

## 9. Incident 4 — Eval không chạy được

### Dấu hiệu

`eval_retrieval.py` báo lỗi collection hoặc dependency.

### Cách kiểm tra

1. pipeline run có đến bước embed hay không
2. `CHROMA_DB_PATH` và `CHROMA_COLLECTION` có trùng với lúc publish không
3. dependencies `chromadb` và `sentence-transformers` đã cài chưa

### Cách xử lý

Chạy lại:

```bash
python etl_pipeline.py run --run-id rebuild-index
python eval_retrieval.py --out artifacts/eval/eval_rebuild.csv
```

## 10. Peer review 3 câu hỏi

Ba câu hỏi này có thể dùng cho Sprint 4 peer review:

1. Nếu `run_timestamp` mới nhưng `latest_exported_at` cũ, team nên sửa pipeline hay sửa source export trước? Vì sao?
2. Vì sao pipeline phải `prune stale ids` trước khi hoặc cùng lúc publish snapshot mới?
3. Trong ngữ cảnh nào `--skip-validate` là chấp nhận được, và vì sao không nên dùng nó cho run chính thức?

## 11. Definition of done cho phần vận hành

Sprint 4 phần docs/runbook được xem là xong khi:

1. có một lệnh chạy toàn pipeline
2. có hướng dẫn đọc PASS / WARN / FAIL của freshness
3. có ít nhất một playbook xử lý incident
4. peer review 3 câu hỏi đã được ghi lại trong runbook hoặc group report
