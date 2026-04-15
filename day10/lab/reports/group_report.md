# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Day10 Data Pipeline Team  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Nguyễn Duy Minh Hoàng | Ingestion / Pipeline Owner | — |
| Đào Anh Quân | Cleaning & Quality Owner | anhquan7303qqq@gmail.com |
| Nguyễn Đôn Đức | Embed & Eval Owner | — |
| Nguyễn Lê Minh Luân | Monitoring / Docs Owner | — |
| Vũ Quang Phúc | Sprint 4 Docs & Reporting Completion | — |

**Ngày nộp:** 2026-04-15  
**Repo:** `Day8-Lab8-9-10/day10/lab`

---

## 1. Pipeline tổng quan

Nguồn raw của nhóm là file `data/raw/policy_export_dirty.csv`, mô phỏng batch export từ hệ nguồn trước khi publish lại vào vector store. Pipeline được chạy bằng một lệnh `python etl_pipeline.py run`, sau đó dữ liệu đi qua các bước `load_raw_csv()` -> `clean_rows()` -> `run_expectations()` -> `cmd_embed_internal()` -> ghi `manifest_<run_id>.json` -> kiểm tra freshness. `run_id` được sinh từ tham số `--run-id` hoặc UTC timestamp và được lưu trong manifest, cleaned CSV, quarantine CSV, cũng như metadata khi upsert vào Chroma collection `day10_kb`.

Về artifact, nhóm dùng ba loại evidence chính: `artifacts/cleaned/` và `artifacts/quarantine/` để chứng minh quá trình clean, `artifacts/manifests/` để theo dõi lineage và freshness, và `artifacts/eval/` để đo before/after retrieval. Sample run ổn định nhất hiện có là `sprint2` và `2026-04-15T08-50Z`, đều cho cùng kết quả `raw_records=10`, `cleaned_records=6`, `quarantine_records=4`. Điều đó cho thấy pipeline không chỉ chạy được mà còn giữ được snapshot publish nhất quán cho các sprint sau.

**Lệnh chạy một dòng:**

```bash
python etl_pipeline.py run
```

---

## 2. Cleaning & expectation

Baseline pipeline đã có các rule cần thiết cho bài lab: allowlist `doc_id`, chuẩn hoá ngày hiệu lực, loại bản HR cũ, loại text rỗng, dedupe, và fix refund window 14 -> 7 ngày. Trên nền đó, nhóm mở rộng thêm Rule 7 phát hiện BOM/ký tự vô hình, Rule 8 chặn ngày hiệu lực vượt `FUTURE_DATE_CUTOFF`, Rule 9 chuẩn hoá whitespace; đồng thời bổ sung E7, E8, E9 ở tầng expectation để tách biệt rõ `halt` và `warn`.

Nhóm chọn các expectation `halt` cho những lỗi có thể làm agent đọc sai mà không tự nhận ra, gồm `min_one_row`, `no_empty_doc_id`, `refund_no_stale_14d_window`, `effective_date_iso_yyyy_mm_dd`, `hr_leave_no_stale_10d_annual`, và `no_bom_or_invisible_char_in_cleaned`. Các expectation `warn` được dùng cho future-dated policy và chunk quá ngắn, vì đây là các trường hợp cần review thêm chứ không phải lúc nào cũng sai tuyệt đối.

### 2a. Bảng metric_impact

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ |
|-----------------------------------|------------------|-----------------------------|----------|
| Rule 2 normalize date | Raw row `01/02/2026` chưa đạt ISO | Trong `cleaned_sprint2.csv` đã thành `2026-02-01` | `artifacts/cleaned/cleaned_sprint2.csv` |
| Rule 3 HR stale cutoff | Raw có row HR 2025, nếu giữ lại sẽ gây conflict 10 vs 12 ngày | Row này vào quarantine với reason `stale_hr_policy_effective_date` | `artifacts/quarantine/quarantine_sprint2.csv` |
| Rule 6 + E3 refund stale window | Khi inject, retrieval vẫn chạm chunk cấm | `hits_forbidden`: `yes` -> `no` sau clean | `artifacts/eval/eval_injected.csv`, `artifacts/eval/eval_clean.csv` |
| E5 ISO date check | Trước clean có ngày kiểu `DD/MM/YYYY` | Sau clean `non_iso_rows=0`, pipeline pass | `cleaned_sprint2.csv`, manifest `sprint2` |
| Rule 7/8/9 + E7/E8/E9 | Baseline sample không kích hoạt các case BOM/future/whitespace | Nhóm ghi rõ inject scenario và `metric_impact` trong contract để chứng minh tác động | `contracts/data_contract.yaml` |

**Rule chính (baseline + mở rộng):**

- Allowlist `doc_id` để chặn source lạ.
- Parse `effective_date` về `YYYY-MM-DD`.
- Loại `hr_leave_policy` cũ hơn `HR_LEAVE_MIN_EFFECTIVE_DATE`.
- Quarantine row thiếu ngày hoặc thiếu `chunk_text`.
- Deduplicate theo normalized text.
- Fix `policy_refund_v4` từ `14 ngày làm việc` sang `7 ngày làm việc`.
- Chặn BOM / invisible characters, future date cutoff, và chuẩn hoá whitespace.

**Ví dụ 1 lần expectation fail và cách xử lý:**

Run `inject-bad` dùng `--no-refund-fix --skip-validate`, nên `refund_no_stale_14d_window` sẽ fail về mặt logic business. Nhóm dùng run này để tạo evidence xấu cho Sprint 3, sau đó chạy lại pipeline chuẩn để publish snapshot sạch và loại chunk stale khỏi top-k retrieval.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent

Kịch bản inject của nhóm tập trung vào policy refund vì đây là lỗi “nghe có vẻ đúng” nhưng có thể làm agent trả lời sai ngay cả khi top-1 vẫn trông hợp lệ. Nhóm chạy `inject-bad` với `no_refund_fix=true` và `skipped_validate=true` theo `artifacts/manifests/manifest_inject-bad.json`. Kết quả là collection vẫn được publish, nhưng top-k retrieval cho câu `q_refund_window` chứa chunk cấm “14 ngày làm việc”.

Ở file `artifacts/eval/eval_injected.csv`, câu `q_refund_window` có `contains_expected=yes` nhưng `hits_forbidden=yes`. Điều này quan trọng vì nó chứng minh top-1 nhìn bề ngoài vẫn đúng, nhưng retrieval context toàn cục vẫn bị nhiễm dữ liệu stale. Sau khi nhóm chạy lại pipeline chuẩn và đánh giá bằng `artifacts/eval/eval_clean.csv`, cùng câu hỏi đó chuyển sang `contains_expected=yes` và `hits_forbidden=no`. Nói cách khác, dữ liệu sai đã bị loại khỏi top-k chứ không chỉ bị đẩy xuống hạng thấp hơn.

Nhóm cũng dùng `q_leave_version` làm bằng chứng bổ sung cho version control. Trong `eval_clean.csv`, kết quả là `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`, cho thấy bản HR 2026 được giữ lại còn bản HR 2025 bị loại qua quarantine. Đây là điểm giúp nhóm đạt chất lượng tốt hơn baseline vì không chỉ sửa một policy đơn lẻ mà còn bảo vệ consistency theo version.

**Kịch bản inject:**

- Chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`
- So sánh với run sạch qua `eval_injected.csv` và `eval_clean.csv`

**Kết quả định lượng:**

- `q_refund_window`: `hits_forbidden=yes` -> `hits_forbidden=no`
- `q_leave_version`: giữ `top1_doc_expected=yes` ở run sạch
- Số record không đổi giữa inject và clean: `raw=10`, `cleaned=6`, `quarantine=4`

---

## 4. Freshness & monitoring

Nhóm dùng SLA freshness mặc định 24 giờ theo `FRESHNESS_SLA_HOURS=24`. Boundary đo là `latest_exported_at` trong manifest, không phải lúc chạy cron. Điều này giúp phân biệt “pipeline mới chạy” với “dữ liệu nguồn vẫn cũ”. Với sample manifest `manifest_2026-04-15T08-50Z.json`, `latest_exported_at` là `2026-04-10T08:00:00`, nên khi chạy `python etl_pipeline.py freshness --manifest ...`, kết quả là `FAIL` vì snapshot đã cũ hơn 24 giờ.

Theo implementation hiện tại, `PASS` nghĩa là timestamp hợp lệ và còn trong SLA; `FAIL` nghĩa là timestamp hợp lệ nhưng quá hạn; `WARN` chỉ xảy ra khi timestamp thiếu hoặc parse lỗi. Sprint 4 của nhóm tập trung tài liệu hoá điểm này trong `docs/runbook.md`, `docs/data_contract.md`, và `docs/pipeline_architecture.md` để người vận hành không hiểu sai freshness.

---

## 5. Liên hệ Day 09

Dữ liệu sau khi publish ở Day 10 hoàn toàn có thể phục vụ lại Day 09, vì collection `day10_kb` là lớp knowledge base mà agent truy xuất. Ý nghĩa của Day 10 là bảo vệ “data layer” trước khi agent đọc. Nếu không clean, agent Day 09 vẫn có thể orchestration đúng nhưng trả lời sai vì context stale. Vì vậy nhóm xem Day 10 là lớp bảo hiểm dữ liệu cho Day 08 / Day 09 chứ không phải một pipeline tách rời.

---

## 6. Rủi ro còn lại & việc chưa làm

- Freshness mới đo một boundary, chưa có tách biệt ingest boundary và publish boundary.
- Chưa có alert ngoài console log.
- Chưa có script auto-check độ đồng bộ giữa docs markdown, YAML contract và code allowlist.
- Một số inject scenario cho Rule 7/8/9 mới được mô tả trong contract và code comments, chưa có artifact riêng commit kèm trong repo.
