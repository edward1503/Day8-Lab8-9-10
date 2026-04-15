# Runbook — Lab Day 10: Incident Response (tối giản)

**Version:** 1.0  
**Cập nhật:** 2026-04-15  
**Owner:** Lab Day 10 Group  
**Timebox incident triage:** 20 phút trước khi escalate / rollback

---

## Incident #1 — Agent trả lời sai cửa sổ hoàn tiền ("14 ngày" thay vì "7 ngày")

### Symptom

User / agent trả lời: *"Bạn có 14 ngày làm việc để yêu cầu hoàn tiền"* thay vì 7 ngày.  
Hoặc eval CSV có: `q_refund_window | hits_forbidden=yes`.

---

### Detection

| Metric | Cách kiểm tra | Giá trị báo lỗi |
|--------|--------------|-----------------|
| `hits_forbidden` trong eval | `cat artifacts/eval/eval_*.csv` | `yes` cho `q_refund_window` |
| Expectation E3 | Log pipeline | `expectation[refund_no_stale_14d_window] FAIL (halt)` |
| Manifest `no_refund_fix` | `cat artifacts/manifests/manifest_<run-id>.json` | `"no_refund_fix": true` |
| Log pipeline | `tail -50 artifacts/logs/run_<run-id>.log` | `PIPELINE_HALT` hoặc `--skip-validate` |

**Triage nhanh (0–5'):**
```bash
# Kiểm tra run cuối
ls -lt artifacts/manifests/ | head -3
cat artifacts/manifests/manifest_<run-id>.json | python -m json.tool

# Xem expectation
grep "expectation\|PIPELINE\|freshness" artifacts/logs/run_<run-id>.log
```

---

### Diagnosis

| Bước | Thời gian | Việc làm | Kết quả mong đợi |
|------|-----------|----------|------------------|
| 1 | 0–5' | Đọc `artifacts/manifests/manifest_<run-id>.json` — kiểm tra `no_refund_fix` và `skipped_validate` | `no_refund_fix: true` → xác nhận pipeline chạy với inject flag |
| 2 | 5–8' | Mở `artifacts/quarantine/quarantine_<run-id>.csv` — đếm records, check reason | Nếu quarantine ít bất thường → cleaning rules không chạy đủ |
| 3 | 8–12' | Mở `artifacts/cleaned/cleaned_<run-id>.csv` — tìm "14 ngày làm việc" trong chunk_text | Tìm thấy → Rule 6 không áp dụng; không tìm thấy → vấn đề ở vector store |
| 4 | 12–15' | Chạy `python eval_retrieval.py --out artifacts/eval/debug_eval.csv` | `hits_forbidden=yes` → vector store vẫn chứa chunk stale |
| 5 | 15–20' | Kiểm tra Chroma collection trực tiếp | `chroma_db/` có data từ run inject → cần prune + re-embed |

**Root cause phổ biến:**

```
Pipeline chạy với --no-refund-fix --skip-validate (Sprint 3 inject)
→ cleaned CSV chứa "14 ngày làm việc"
→ upsert vào Chroma với chunk_id mới (vì text khác)
→ run chuẩn sau đó KHÔNG prune chunk cũ đúng cách
   hoặc chưa chạy lại pipeline chuẩn
```

---

### Mitigation

**Bước 1 — Rollback ngay (< 5'):**
```bash
# Re-run pipeline chuẩn (không inject flag)
cd day10/lab
python etl_pipeline.py run --run-id fix-$(date -u +%Y-%m-%dT%H-%MZ)
```

Pipeline chuẩn sẽ:
1. Apply Rule 6 (fix "14 ngày" → "7 ngày")
2. Chạy E3 halt (kiểm tra không còn "14 ngày")
3. Prune stale vectors (xóa chunk_id từ run inject)
4. Upsert 6 chunks sạch

**Bước 2 — Verify:**
```bash
python eval_retrieval.py --out artifacts/eval/after_fix.csv
grep "q_refund_window" artifacts/eval/after_fix.csv
# Mong đợi: contains_expected=yes, hits_forbidden=no
```

**Bước 3 — Nếu pipeline tiếp tục FAIL (expectation halt):**
```bash
# Kiểm tra log chi tiết
tail -100 artifacts/logs/run_fix-*.log

# Thủ công xóa Chroma collection nếu state corrupt
python -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
client.delete_collection('day10_kb')
print('Collection deleted — re-run pipeline to rebuild')
"
python etl_pipeline.py run
```

**Tạm thời (nếu không fix được trong 20'):**
- Đặt banner "Thông tin chính sách hoàn tiền đang được cập nhật — vui lòng liên hệ CS trực tiếp"
- Ghi incident ticket với `run_id` của lần inject và lần fix

---

### Prevention

| Hành động | Loại | Chi tiết |
|-----------|------|---------|
| Thêm pre-run check | Code | Kiểm tra `--no-refund-fix` không được dùng trong prod; fail fast với warning rõ ràng |
| Thêm expectation E3 alert | Monitoring | Khi E3 FAIL → gửi alert (hiện tại chỉ log console) |
| Ghi incident vào `reports/group_report.md` | Process | Ghi `run_id` inject + `run_id` fix + before/after eval để traceability |
| Thêm `hits_forbidden` check vào CI | Quality gate | Sau mỗi pipeline run, tự động chạy `eval_retrieval.py` và fail nếu `hits_forbidden=yes` |
| Phân biệt môi trường | Architecture | Sprint 3 inject chỉ chạy trên collection tách biệt (`day10_kb_test`) — không đụng `day10_kb` prod |

---

## Incident #2 — Freshness FAIL (age_hours > 24)

### Symptom

Log pipeline: `freshness_check=FAIL {"age_hours": 120.862, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`

### Detection

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
# Output: FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 120.862, ...}
```

### Diagnosis

| Kiểm tra | Lệnh | Ý nghĩa |
|----------|------|---------|
| `latest_exported_at` | `cat manifest_<run-id>.json \| python -m json.tool` | Timestamp export từ nguồn — đây là boundary đo |
| Delta `exported_at` vs `run_timestamp` | So sánh 2 trường trong manifest | Nếu `run_timestamp` mới nhưng `exported_at` cũ → vấn đề ở nguồn, không phải pipeline |
| Nguồn CSV | Kiểm tra `data/raw/policy_export_dirty.csv` | `exported_at` column — tất cả rows có cùng timestamp? |

**Lưu ý CSV mẫu:** `exported_at = 2026-04-10` (cố ý cũ để demo SLA breach). Đây là **expected behavior** trong lab.

### Mitigation

```bash
# Option 1: Tăng SLA trong .env (chỉ dùng cho lab/demo)
echo "FRESHNESS_SLA_HOURS=200" >> .env
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
# → PASS

# Option 2: Re-export data với timestamp mới (production path)
# Cập nhật exported_at trong CSV nguồn → re-run pipeline
```

### Prevention

- Đo freshness tại **2 boundary**: `ingest_boundary` (khi đọc CSV) + `publish_boundary` (sau embed) → Bonus +1 nếu implement.
- Alert khi `age_hours > sla * 0.8` (pre-warning threshold trước khi breach thật).

---

## Incident #3 — Pipeline HALT (expectation fail)

### Symptom

Log: `PIPELINE_HALT: expectation suite failed (halt).`

### Detection

```bash
grep "FAIL (halt)\|PIPELINE_HALT" artifacts/logs/run_<run-id>.log
```

### Diagnosis — Theo từng expectation

| Expectation FAIL | Root cause | Action |
|-----------------|------------|--------|
| `min_one_row` FAIL | Raw CSV rỗng hoặc tất cả rows bị quarantine | Kiểm tra `quarantine_<run-id>.csv` — tất cả bị loại vì lý do gì? |
| `no_empty_doc_id` FAIL | Header CSV đổi tên cột (breaking change) | Kiểm tra column names trong raw CSV; cập nhật parser |
| `refund_no_stale_14d_window` FAIL | Run inject chạy nhưng validate không skip | Đảm bảo không dùng `--no-refund-fix` trong prod |
| `effective_date_iso_yyyy_mm_dd` FAIL | Rule 2 parse lỗi — format mới không được hỗ trợ | Thêm format vào `_normalize_effective_date()` |
| `hr_leave_no_stale_10d_annual` FAIL | Bản HR 2025 vào được cleaned (Rule 3 cutoff sai) | Kiểm tra `HR_LEAVE_MIN_EFFECTIVE_DATE` trong `.env` |
| `no_bom_or_invisible_char_in_cleaned` FAIL | Rule 7 bị bypass hoặc tắt | Kiểm tra `_INVISIBLE_CHARS` và Rule 7 trong cleaning_rules.py |

### Mitigation

```bash
# Chạy với --skip-validate CHỈ để debug (không prod)
python etl_pipeline.py run --skip-validate --run-id debug-$(date -u +%Y-%m-%dT%H-%MZ)

# Kiểm tra cleaned CSV để tìm root cause
python -c "
import csv
with open('artifacts/cleaned/cleaned_debug-*.csv') as f:
    rows = list(csv.DictReader(f))
    print(f'rows={len(rows)}')
    for r in rows: print(r)
"
```

### Prevention

- Sau mỗi incident HALT: **thêm ít nhất 1 expectation mới** để bắt trường hợp tương tự trong tương lai (không chỉ blame người).
- Ghi lý do và expectation mới vào `reports/group_report.md` section "metric_impact".

---

## Tham chiếu nhanh

```bash
# Pipeline chuẩn
python etl_pipeline.py run

# Kiểm tra freshness
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json

# Eval retrieval
python eval_retrieval.py --out artifacts/eval/check_$(date -u +%Y%m%d).csv

# Xem log gần nhất
ls -t artifacts/logs/ | head -1 | xargs -I{} cat artifacts/logs/{}

# Xem quarantine gần nhất
ls -t artifacts/quarantine/ | head -1 | xargs -I{} cat artifacts/quarantine/{}
```
