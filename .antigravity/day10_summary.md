# Day 10 — Data Pipeline & Data Observability
> **Khóa học:** AI in Action (AICB-P1) · **Tiếp nối:** Day 08 (RAG) → Day 09 (Multi-agent) → Day 10 (Data Layer)
> **Tài liệu gốc:** `day10/lecture-10.html` (46 slides) · `day10/INSTRUCTOR_GUIDE_DAY10.md` · `day10/lab/`

---

## 1. Bức tranh tổng quan

Day 10 trả lời câu hỏi: **"Agent Day 09 có câu trả lời đúng không phụ thuộc vào corpus Day 10 có sạch và tươi không?"**

Stack AI production đầy đủ gồm 4 tầng:
```
Sources → Pipeline (ingest → clean → validate) → Storage/Serving (Vector DB) → Agent
```
Vector store **phản chiếu** chất lượng của tầng dưới nó. Nếu pipeline hỏng thì agent "hallucinate" không phải do model mà do **dữ liệu stale / sai version**.

**Tư duy chủ đạo của buổi:**
> 🔑 *Đừng debug model trước — hãy kiểm tra theo thứ tự:*
> **Freshness → Volume → Schema → Lineage → rồi mới đến model/prompt**

**Case study xuyên suốt 3 ngày:** CS + IT Helpdesk với 3 domain:
- `policy_refund_v4`: hoàn tiền **7 ngày** (bị lỗi sync thành 14 ngày)
- `sla_p1_2026`: SLA ticket P1 phản hồi 15 phút
- `hr_leave_policy`: phép năm **12 ngày** bản 2026 (vs bản cũ 10 ngày)
- `it_helpdesk_faq`: khóa tài khoản sau 5 lần sai

---

## 2. Lý thuyết — 46 Slides

### Phần A (Slides 1–11): Nền tảng & Pipeline Thinking

| Concept | Nội dung cốt lõi |
|---------|-----------------|
| **Observability ≠ Dashboard** | Dashboard là triệu chứng; observability là **suy luận nguyên nhân** (có giả thuyết + bằng chứng) |
| **AI = Model + Data Path + Serving** | Mọi lỗi agent đều phải kiểm tra tầng data trước |
| **RACI tối giản** | Startup nhỏ: 1 người nhiều vai được, nhưng **phải có tên owner trên artifact** |
| **SLA freshness** | Gắn điểm đo cụ thể (sau clean? sau publish index?) + ngôn ngữ nghiệp vụ (≤ 4h sau PDF ký) |
| **Checklist trước khi embed** | Schema, encoding (UTF-8 + tiếng Việt), version metadata, skim 20 dòng + golden query |
| **ETL vs ELT** | Phụ thuộc **nơi transform** và **ai được xem raw** (governance + khả năng SQL trên lake) |

**Phân tầng lỗi agent:**
- `Câu trả lời cũ` → nghi Freshness
- `Trích sai nguồn` → nghi Dedupe / Parser
- `Spike sau deploy` → nghi Schema / Parser mới
- `Retrieval gap` (chunk đúng nhưng rank sai) ≠ `Data bug` (chunk sai)

---

### Phần B (Slides 12–20): Ingestion

| Concept | Chi tiết |
|---------|----------|
| **CDC vs Snapshot** | Snapshot + watermark: đơn giản, độ trễ cao; CDC (Debezium/Kafka): thấp hơn nhưng phức tạp hơn |
| **API Ingestion** | Retry-After, backoff + **jitter** (tránh Thundering Herd), cursor pagination, checkpoint, DLQ |
| **Files PDF/HTML** | Content hash vs logical version; OCR confidence; chunk theo heading (tránh trộn điều khoản) |
| **Queue / Backpressure / DLQ** | Queue depth = signal; DLQ không phải thùng rác — là **không mất sự kiện** cần replay |
| **Source Map** | Khung 3 câu: Nguồn nào · Hỏng kiểu gì · Đo cái gì |

> ⚠️ **Hay nhầm:** Đo freshness ở `cron_start` thay vì `index_visible` → "pipeline green nhưng user vẫn thấy cũ"

---

### Phần C (Slides 21–30): Transform, Quality & Observability

#### Transform & Dirty Data
| Rule | Lý do |
|------|-------|
| Deduplicate chunk_text | Duplicate vector → nhiễu retrieval |
| Chuẩn hoá encoding UTF-8 | Tiếng Việt bị lỗi → khác nhau về embedding distance |
| Chuẩn hoá date format | ISO8601 bắt buộc sau clean |
| Quarantine vs Silent Drop | Quarantine: dữ liệu quan trọng nhưng lỗi; Silent drop: rác hoàn toàn |

#### 5 Pillars of Data Observability (Monte Carlo model)
```
1. Freshness    — Dữ liệu có tươi theo SLA không?
2. Volume       — Số record có đúng ngưỡng kỳ vọng không?
3. Distribution — Phân phối có bình thường không? (volume ổn ≠ distribution ổn)
4. Schema       — Cột/type có đổi không? (additive vs breaking)
5. Lineage      — Dữ liệu đến từ đâu, qua bước nào?
```

#### Warn / Quarantine / Halt (3 mức xử lý)
- **Warn**: lỗi nhỏ, không chặn pipeline, log để theo dõi (`< 1%` null tag phụ)
- **Quarantine**: isolate record lỗi để xem xét lại, agent không đọc
- **Halt**: vi phạm data contract nghiêm trọng (mất cột ID, encoding corrupt, duplicate khóa chính quy mô lớn)

> 💡 Halt quá nhiều → pipeline không bao giờ xanh → cần **SLO error budget** cho data

#### Schema Evolution
- **Additive** (thêm cột): không breaking nếu parser tolerant
- **Breaking** (đổi tên cột, xóa cột): ảnh hưởng ingestion + SQL transform + metadata filter RAG
- Đổi tên `customer_id` → `cust_id` = breaking ở mọi tầng stack

#### SLI gợi ý cho RAG/Agent
- Citation freshness (metadata version của chunk được trích dẫn)  
- Grounding rate (% câu trả lời có source hợp lệ)
- Hit@k golden (golden question set)
- Latency pipeline **tách biệt** latency LLM (sai chỗ tối ưu nếu gộp)

---

### Phần D (Slides 31–37): Orchestration, Idempotency & Runbook

#### Incident Triage có Timebox
```
0–5'   : Đọc Freshness SLA (thời gian nạp cuối của vector index)
5–12'  : Volume & errors (rows_ingested vs vectors_upserted)
12–20' : Schema & lineage (data contract diff, run_id trace)
> 20'  : Mitigate (rollback bản sạch gần nhất, banner "đang bảo trì") + ghi incident
```
> Trong P1 có thể **rollback trước** rồi mới tìm root cause

#### Idempotency Patterns
| Pattern | Ứng dụng |
|---------|----------|
| Natural key upsert | Embed theo `chunk_id` ổn định (hash nội dung + doc_id + seq) |
| Partition overwrite | Batch replace toàn bộ partition ngày |
| Staging → swap alias | Blue/green index: atomic, không downtime đang serve |
| Prune stale vectors | Xóa id không còn trong cleaned sau mỗi publish run |

> ⚠️ `uuid` ngẫu nhiên mỗi lần embed = không idempotent → phình collection khi rerun

#### Orchestrator Mental Model
- **Trigger**: điều kiện khởi chạy (cron, event)
- **Sensor**: chờ upstream sẵn sàng (file xuất hiện trên S3, table partition ready)
- **DAG dependency**: không tranh luận Airflow vs Prefect — cùng câu hỏi: dependency + alert + idempotency

#### Runbook Post-Incident (5 bước)
```
Symptom → Detection → Diagnosis → Mitigation → Prevention
```
Prevention: thêm expectation sau sự cố (không chỉ blame người)

---

## 3. Lab — Cấu trúc & Sprint

### Bối cảnh
`data/raw/policy_export_dirty.csv` — 11 dòng raw có các lỗi cố ý:

| Dòng | Lỗi | Xử lý |
|------|-----|-------|
| chunk 2 | Duplicate với chunk 1 | Quarantine: `duplicate_chunk_text` |
| chunk 3 | Cửa sổ hoàn tiền **14 ngày** (lẽ ra 7 ngày) | Fix text: `14 ngày` → `7 ngày` hoặc quarantine nếu `--no-refund-fix` |
| chunk 5 | `chunk_text` rỗng | Quarantine: `missing_chunk_text` |
| chunk 7 | HR policy **2025**, 10 ngày (bản cũ) | Quarantine: `stale_hr_policy_effective_date` |
| chunk 9 | `doc_id = legacy_catalog_xyz_zzz` không trong allowlist | Quarantine: `unknown_doc_id` |
| chunk 10 | Ngày format `01/02/2026` (DD/MM/YYYY) | Parse → chuẩn hoá → `2026-02-01` |

**Dữ liệu sau clean (kỳ vọng baseline):** ~6 dòng hợp lệ.

---

### Sprint 1 (60') — Ingest & Schema
- Đọc `data/raw/policy_export_dirty.csv`
- Điền source map trong `docs/data_contract.md` (≥2 nguồn / failure mode / metric)
- Chạy: `python etl_pipeline.py run --run-id sprint1`
- **DoD:** Log có `raw_records`, `cleaned_records`, `quarantine_records`, `run_id`

### Sprint 2 (60') — Clean + Validate + Embed
- Thêm **≥ 3 rule mới** vào `transform/cleaning_rules.py`
- Thêm **≥ 2 expectation mới** vào `quality/expectations.py`
- Mỗi rule/expectation mới phải ghi `metric_impact` trong `reports/group_report.md`
- Embed idempotent (upsert `chunk_id` + prune stale id sau publish)
- **DoD:** `python etl_pipeline.py run` exit 0 (không halt)

### Sprint 3 (60') — Inject Corruption & Before/After
```bash
# Inject: nhúng dữ liệu "xấu"
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv

# Clean: chạy pipeline chuẩn
python etl_pipeline.py run
python eval_retrieval.py --out artifacts/eval/after_clean.csv
```
- **DoD:** Có đoạn văn + số liệu: retrieval **tệ hơn** trước fix và **tốt hơn** sau fix (ít nhất `q_refund_window`)
- **Merit:** Thêm evidence cho `q_leave_version` (HR 12 vs 10 ngày)

### Sprint 4 (60') — Monitoring + Docs + Báo cáo
- `python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json`
- Hoàn thiện 3 docs: `pipeline_architecture.md`, `data_contract.md`, `runbook.md`
- Hoàn thiện `reports/group_report.md` & `reports/individual/<ten>.md`
- **DoD:** README có "một lệnh chạy cả pipeline"; peer review 3 câu ghi trong report

---

## 4. Code Components

### `etl_pipeline.py` — Entrypoint chính
```
Luồng: ingest → clean → validate → embed → manifest → freshness check
```
**Args quan trọng:**
- `--run-id`: định danh run (default: UTC timestamp)
- `--no-refund-fix`: bỏ qua rule fix 14→7 ngày (dùng cho inject Sprint 3)
- `--skip-validate`: tiếp tục embed dù expectation halt (chỉ demo)

**Output bắt buộc trong log:**
```
run_id=...
raw_records=...
cleaned_records=...
quarantine_records=...
expectation[<name>] OK|FAIL (warn|halt) :: <detail>
freshness_check=PASS|WARN|FAIL {...}
PIPELINE_OK | PIPELINE_HALT
```

**Manifest JSON** (lưu tại `artifacts/manifests/`):
```json
{
  "run_id": "2026-04-15T07-00Z",
  "raw_records": 11,
  "cleaned_records": 6,
  "quarantine_records": 5,
  "latest_exported_at": "2026-04-10T08:00:00",
  "no_refund_fix": false,
  "skipped_validate": false,
  "chroma_collection": "day10_kb"
}
```

---

### `transform/cleaning_rules.py` — 6 Rules Baseline
| # | Rule | Xử lý |
|---|------|--------|
| 1 | `doc_id` không trong `ALLOWED_DOC_IDS` | Quarantine: `unknown_doc_id` |
| 2 | `effective_date` không parse được | Quarantine: `missing/invalid_effective_date` |
| 3 | `hr_leave_policy` với date < 2026-01-01 | Quarantine: `stale_hr_policy_effective_date` |
| 4 | `chunk_text` rỗng | Quarantine: `missing_chunk_text` |
| 5 | Trùng nội dung `chunk_text` (normalize) | Quarantine: `duplicate_chunk_text` |
| 6 | `policy_refund_v4` chứa "14 ngày làm việc" | Fix text: thay bằng "7 ngày làm việc" + tag `[cleaned: stale_refund_window]` |

**`chunk_id` ổn định:**
```python
sha256(f"{doc_id}|{chunk_text}|{seq}").hexdigest()[:16]
→ "{doc_id}_{seq}_{hash}"
```
Đảm bảo rerun cho **cùng nội dung** → cùng `chunk_id` → upsert idempotent.

**Hỗ trợ date format:**
- `YYYY-MM-DD` → pass-through
- `DD/MM/YYYY` → normalize sang ISO

---

### `quality/expectations.py` — 6 Expectations Baseline
| ID | Severity | Kiểm tra |
|----|----------|---------|
| `min_one_row` | **halt** | ≥ 1 dòng sau clean |
| `no_empty_doc_id` | **halt** | Không có `doc_id` rỗng |
| `refund_no_stale_14d_window` | **halt** | `policy_refund_v4` không chứa "14 ngày làm việc" |
| `chunk_min_length_8` | warn | `chunk_text` ≥ 8 ký tự |
| `effective_date_iso_yyyy_mm_dd` | **halt** | Đúng regex `^\d{4}-\d{2}-\d{2}$` |
| `hr_leave_no_stale_10d_annual` | **halt** | `hr_leave_policy` không chứa "10 ngày phép năm" |

---

### `monitoring/freshness_check.py`
Đọc `latest_exported_at` từ manifest → tính `age_hours` → so với `FRESHNESS_SLA_HOURS` (default 24h):
- `age_hours ≤ sla_hours` → **PASS**
- Không có timestamp → **WARN**
- `age_hours > sla_hours` → **FAIL**

> ℹ️ CSV mẫu có `exported_at = 2026-04-10` → **FAIL là hợp lý và có chủ đích** — nhóm ghi giải thích trong runbook.

---

### `eval_retrieval.py` — Before/After Eval
Truy vấn Chroma với `test_questions.json` (4 câu golden), output CSV:
```
question_id | contains_expected | hits_forbidden | top1_doc_id | top1_doc_expected
```

**4 câu golden:**
| ID | Câu hỏi | Kỳ vọng |
|----|---------|---------|
| `q_refund_window` | Số ngày hoàn tiền? | Chứa "7 ngày", KHÔNG chứa "14 ngày làm việc" |
| `q_p1_sla` | SLA P1 là bao lâu? | Chứa "15 phút" |
| `q_lockout` | Bao nhiêu lần sai thì khóa? | Chứa "5 lần" |
| `q_leave_version` | Phép năm 2026 dưới 3 năm? | Chứa "12 ngày", top-1 = `hr_leave_policy` |

---

### `grading_run.py` — Chấm điểm tự động
Chạy 3 câu grading (`gq_d10_01`, `gq_d10_02`, `gq_d10_03`) → xuất `grading_run.jsonl`:
```json
{"id": "gq_d10_01", "contains_expected": true, "hits_forbidden": false, "top1_doc_matches": null}
{"id": "gq_d10_02", "contains_expected": true, "hits_forbidden": false, "top1_doc_matches": null}
{"id": "gq_d10_03", "contains_expected": true, "hits_forbidden": false, "top1_doc_matches": true}
```
> `hits_forbidden` quét **toàn bộ top-k** (không chỉ top-1) — phát hiện "context đúng nhưng vẫn còn chunk stale".

---

## 5. Cấu trúc thư mục Lab

```
lab/
├── etl_pipeline.py           ← Entrypoint chính (Sprint 1–2)
├── eval_retrieval.py         ← Before/after eval (Sprint 3–4)
├── grading_run.py            ← Chấm điểm JSONL
├── instructor_quick_check.py ← GV sanity check artifact
├── transform/
│   └── cleaning_rules.py     ← 6 baseline rules (SV thêm ≥3)
├── quality/
│   └── expectations.py       ← 6 baseline expectations (SV thêm ≥2)
├── monitoring/
│   └── freshness_check.py    ← SLA freshness từ manifest
├── contracts/
│   └── data_contract.yaml    ← Schema + SLA + allowed_doc_ids
├── data/
│   ├── docs/                 ← 5 tài liệu nguồn (.txt)
│   ├── raw/policy_export_dirty.csv  ← Dữ liệu dirty 11 dòng
│   ├── test_questions.json   ← 4 câu golden (eval_retrieval)
│   └── grading_questions.json ← 3 câu chấm (grading_run)
├── artifacts/
│   ├── logs/                 ← run_*.log
│   ├── manifests/            ← manifest_*.json
│   ├── quarantine/           ← quarantine_*.csv
│   ├── cleaned/              ← cleaned_*.csv
│   └── eval/                 ← before_after_eval.csv, grading_run.jsonl
├── docs/
│   ├── pipeline_architecture.md
│   ├── data_contract.md
│   ├── runbook.md
│   └── quality_report_template.md → quality_report.md
└── reports/
    ├── group_report.md       ← Bảng metric_impact bắt buộc
    └── individual/<ten>.md  ← 400–650 từ mỗi người
```

---

## 6. Data Contract (`contracts/data_contract.yaml`)

```yaml
version: "1.0"
dataset: "kb_chunk_export"
owner_team: "<điền>"

schema_cleaned:
  chunk_id:    {type: string, required: true}
  doc_id:      {type: string, required: true}
  chunk_text:  {type: string, required: true, min_length: 8}
  effective_date: {type: date, required: true}
  exported_at: {type: datetime, required: true}

quality_rules:
  - id: "no_duplicate_chunk_text"     severity: warn
  - id: "no_stale_refund_window"      severity: halt

freshness:
  measured_at: "publish"   # ingest | cleaned | publish
  sla_hours: 24

allowed_doc_ids:
  - policy_refund_v4
  - sla_p1_2026
  - it_helpdesk_faq
  - hr_leave_policy

policy_versioning:
  hr_leave_min_effective_date: "2026-01-01"
```

---

## 7. Rubric & Scoring

### Phần Nhóm (60 điểm)
| Mục | Điểm max |
|-----|----------|
| ETL pipeline exit 0 | 10 |
| Log đủ 4 trường (`run_id`, `raw`, `cleaned`, `quarantine`) | 5 |
| ≥ 3 cleaning rules mới (non-trivial) | 6 |
| Embed idempotent + prune stale vectors | 6 |
| `pipeline_architecture.md` | 5 |
| `data_contract.md` (≥2 nguồn) | 5 |
| `runbook.md` (5 mục) | 5 |
| ≥ 2 expectations mới (non-trivial) | 6 |
| Before/after eval (≥2 dòng CSV) | 6 |
| Quality report (với `run_id`) | 6 |
| Grading JSONL (3 câu) | 0–12 |

### Phân hạng
| Hạng | Điều kiện |
|------|-----------|
| **Pass** | Đủ checklist 1–3; `gq_d10_01` & `gq_d10_02` đúng |
| **Merit** | Pass + `gq_d10_03` đủ 3 tiêu chí + evidence `q_leave_version` |
| **Distinction** | Merit + **một trong**: GE/pydantic validate thật; freshness 2 boundary; LLM-judge eval ≥5 câu; rule versioning không hard-code |

**Chống trivial:** Rule mới không làm thay đổi `quarantine_records` / `cleaned_records` / expectation result / eval trên bất kỳ scenario nào → bị trừ điểm.

### Phần Cá nhân (40 điểm)
| Mục | Điểm |
|-----|------|
| Individual report (400–650 từ): phần phụ trách, 1 quyết định kỹ thuật, 1 sự cố/anomaly, before/after trích log, cải tiến 2h | 30 |
| Code contribution (vai khớp commit, giải thích được, không mâu thuẫn report) | 10 |

**Bonus (+3 max):**
- Tích hợp GE hoặc pydantic validate thật: +2
- Freshness đo 2 boundary (ingest + publish): +1

---

## 8. Quick Reference — Lệnh Thường Dùng

```bash
# Setup
cd day10/lab
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Pipeline chuẩn (Sprint 1–2)
python etl_pipeline.py run
python etl_pipeline.py run --run-id sprint1

# Kiểm tra freshness
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json

# Eval retrieval (before/after)
python eval_retrieval.py --out artifacts/eval/before_after_eval.csv

# Inject corruption (Sprint 3)
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv

# Chấm điểm (sau 17:00)
python grading_run.py --out artifacts/eval/grading_run.jsonl

# GV kiểm tra nhanh
python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl
python instructor_quick_check.py --manifest artifacts/manifests/manifest_<run-id>.json
```

---

## 9. Điểm Chú Ý Quan Trọng

| ⚠️ Hay nhầm | ✅ Đúng |
|------------|---------|
| Embed xong rồi phát hiện encoding lỗi | Kiểm tra encoding **trước** khi embed (quality gate) |
| Freshness đo ở `cron_start` | Đo ở **`index_visible`** (publish boundary) |
| DLQ = thùng rác | DLQ = không mất sự kiện + **cần replay process** |
| `uuid` ngẫu nhiên mỗi lần embed | Dùng **stable key** = hash(doc_id + text + seq) |
| Halt hết mọi lỗi | Phân biệt warn/quarantine/halt theo **SLO error budget** |
| Đổi tên cột không ảnh hưởng | Breaking ở ingestion + SQL + metadata filter RAG |
| Fine-tune model khi corpus cũ | Fix **data tầng dưới** trước — corpus cũ thì fine-tune vô nghĩa |
| `delete all` rồi `insert` trên prod | Dùng **staging → swap alias** (blue/green) |
| Postmortem chỉ blame người | Postmortem phải có **action item trên pipeline** |

---

## 10. Mối Liên Hệ Với Day 08 & Day 09

```
Day 08: RAG grounding
  ↓ corpus quality?
Day 09: Multi-agent orchestration  
  ↓ retrieval worker dùng vector store nào?
Day 10: Data Pipeline & Observability
  → Đảm bảo vector store luôn sạch, tươi, đúng version
```

- **Day 08** đã dùng corpus `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`
- **Day 09** retrieval worker kéo từ vector store — nếu store chứa chunk "14 ngày" thay vì "7 ngày" → agent trả lời sai
- **Day 10** pipeline sửa lỗi này, tạo `before_after_eval.csv` chứng minh cải thiện

---

*Tạo lúc: 2026-04-15 | Nguồn: `day10/INSTRUCTOR_GUIDE_DAY10.md`, `day10/lab/README.md`, `day10/lab/SCORING.md`, source code lab*
