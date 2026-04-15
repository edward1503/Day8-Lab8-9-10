# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Đào Anh Quân - 2A202600028  
**Vai trò:** Cleaning & Quality Owner (Sprint 2)  
**Ngày nộp:** 2026-04-15  
**Độ dài yêu cầu:** **400–650 từ**

---

## 1. Tôi phụ trách phần nào? (~110 từ)

**File / module:**

- `transform/cleaning_rules.py` — Thêm **3 rules mới** (Rule 7: BOM/ký tự vô hình, Rule 8: future date cutoff, Rule 9: whitespace normalization) và nâng cấp Rule 3 (HR cutoff đọc từ env thay vì hard-code, đạt Distinction d).
- `quality/expectations.py` — Thêm **3 expectations mới**: E7 `no_bom_or_invisible_char_in_cleaned` (halt), E8 `no_future_effective_date_beyond_cutoff` (warn), E9 `chunk_text_min_word_count` (warn).
- `contracts/data_contract.yaml` — Bổ sung đầy đủ owner, SLA, canonical sources với failure mode, và đồng bộ 9 rules + 9 expectations với `metric_impact`.

**Kết nối với thành viên khác:**

Tôi nhận baseline pipeline từ Minh Hoàng (Sprint 1) và mở rộng tầng cleaning/validation. Output `cleaned_sprint2.csv` và `quarantine_sprint2.csv` là input cho Embed Owner (Sprint 2–3) và làm nền cho inject corruption ở Sprint 3.

**Bằng chứng:** Commit `2742424`, run log `artifacts/logs/run_sprint2.log`, manifest `artifacts/manifests/manifest_sprint2.json`.

---

## 2. Một quyết định kỹ thuật (~130 từ)

**Quyết định: Rule 7 đặt trước dedup (Rule 5), và severity E7 = halt thay vì warn.**

Khi quyết định vị trí Rule 7 trong pipeline, tôi có hai lựa chọn: kiểm tra BOM trước hoặc sau bước dedup. Nếu đặt sau dedup, một chunk BOM xuất hiện trước bản sạch trong CSV sẽ "giành" slot dedup, khiến bản sạch bị quarantine thay vì bản lỗi. Tôi đặt Rule 7 **sau Rule 4** (empty text) và **trước Rule 5** (dedup) để đảm bảo bản sạch luôn sống sót khi có cả hai.

Về severity của E7, tôi chọn **halt** vì BOM (`\ufeff`) làm lệch embedding vector một cách im lặng — vector store không báo lỗi nhưng similarity search trả về kết quả sai. Khác với E8 và E9 (warn, vì future date và chunk ngắn có thể hợp lệ trong một số trường hợp), BOM không bao giờ là dữ liệu intentional và phải dừng pipeline. E7 đóng vai trò "lưới an toàn thứ hai" sau Rule 7: nếu cleaning bị bypass, expectation vẫn bắt được.

---

## 3. Một lỗi hoặc anomaly đã xử lý (~130 từ)

**Anomaly: E9 FAIL (warn) phát hiện chunk thiếu từ trong inject test.**

Trong quá trình kiểm chứng rules bằng `data/raw/inject_test_rules.csv` (run_id `inject-rules-test`), tôi inject một row `doc_id=sla_p1_2026` với `chunk_text="SLA: xem phụ lục"` — đây là chunk 4 từ, dưới ngưỡng `CHUNK_MIN_WORD_COUNT=5`.

**Triệu chứng phát hiện:**
```
expectation[chunk_text_min_word_count] FAIL (warn) :: short_chunks=1 min_words=5
```
Chunk này vượt qua tất cả baseline rules (doc_id hợp lệ, date đúng, text không rỗng, không trùng) nhưng bị E9 bắt. Pipeline không halt (severity=warn) — đúng thiết kế vì snippet ngắn trong policy có thể là tiêu đề section hợp lệ và cần review thủ công, không nên tự động quarantine.

**Kết quả:** E9 chứng minh tầng expectation bắt được edge case mà tầng rule không xử lý. Tôi ghi nhận `metric_impact` này vào `contracts/data_contract.yaml` và bảng group report.

---

## 4. Bằng chứng trước / sau (~100 từ)

**run_id=`sprint2`** — Pipeline chuẩn trên `policy_export_dirty.csv`:

```
raw_records=10  →  cleaned_records=6  |  quarantine_records=4
expectation[no_bom_or_invisible_char_in_cleaned] OK (halt) :: bom_violations=0
expectation[no_future_effective_date_beyond_cutoff] OK (warn) :: future_date_violations=0
expectation[chunk_text_min_word_count] OK (warn) :: short_chunks=0 min_words=5
embed_upsert count=6 collection=day10_kb
```

**run_id=`inject-rules-test`** — Inject 2 BOM rows + 1 future date + 1 HR stale:

```
raw_records=7  →  cleaned_records=3  |  quarantine_records=4
  [bom_or_invisible_char_in_text] × 2  (Rule 7)
  [effective_date_beyond_future_cutoff] × 1  (Rule 8)
  [stale_hr_policy_effective_date] × 1  (Rule 3 env-based)
expectation[chunk_text_min_word_count] FAIL (warn) :: short_chunks=1
```

**Eval sprint2** (`artifacts/eval/sprint2_eval.csv`): 4/4 câu `contains_expected=yes`, `hits_forbidden=no`, `q_leave_version → top1_doc_expected=yes`.

---

## 5. Cải tiến tiếp theo (~60 từ)

Nếu có thêm 2 giờ, tôi sẽ tích hợp **pydantic model** validate schema của mỗi `cleaned row` sau khi `clean_rows()` hoàn tất — thay thế một phần expectations thủ công bằng type-safe validation. Cụ thể: model `CleanedChunk` với `effective_date: date` (tự parse ISO, fail rõ ràng), `chunk_text: constr(min_length=8)`, và `doc_id: Literal[...]`. Điều này đạt Bonus +2 (pydantic validate thật) và loại bỏ các expectation kiểm tra format mà hiện tại code tự lặp lại logic.
