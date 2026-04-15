"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).

Rules mới (Sprint 2):
  Rule 7 — bom_invisible_char_detection:
      Quarantine chunk có BOM (\\ufeff) hoặc zero-width space (\\u200b) trong chunk_text.
      metric_impact: inject 1 row BOM → quarantine_records tăng 1; không rule này → chunk lọt vào index với ký tự lạ.

  Rule 8 — future_effective_date_cutoff:
      Quarantine chunk có effective_date vượt quá FUTURE_DATE_CUTOFF (đọc từ env, mặc định 2030-01-01).
      Không hard-code ngày cố định — đọc từ env để đổi quyết định clean khi inject (Distinction d).
      metric_impact: inject row '2099-01-01' → quarantine_records tăng 1; thay FUTURE_DATE_CUTOFF=2025-01-01 → rows thêm bị quarantine.

  Rule 9 — excessive_whitespace_normalization:
      Chuẩn hóa nhiều space/tab/newline liên tiếp trong chunk_text thành 1 space, strip đầu/cuối.
      Đánh dấu '[cleaned: whitespace_normalized]' khi text thay đổi.
      metric_impact: inject row có tab/newline thừa → cleaned_records có marker; không rule → text không đồng nhất gây ảnh hưởng embedding similarity.

Distinction (d): HR_LEAVE_MIN_DATE đọc từ env HR_LEAVE_MIN_EFFECTIVE_DATE (mặc định 2026-01-01)
      → thay env var → quyết định clean baseline rule 3 thay đổi mà không cần sửa code.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")

# ── Rule 3 (nâng): đọc từ env thay vì hard-code (Distinction d) ──────────────
# Thay đổi HR_LEAVE_MIN_EFFECTIVE_DATE=2025-01-01 trong .env → bản HR 2025 KHÔNG bị quarantine nữa
# → chứng minh env thay đổi quyết định clean mà không sửa code.
HR_LEAVE_MIN_DATE: str = os.environ.get("HR_LEAVE_MIN_EFFECTIVE_DATE", "2026-01-01")

# ── Rule 8: cutoff ngày tương lai (đọc từ env) ────────────────────────────────
FUTURE_DATE_CUTOFF: str = os.environ.get("FUTURE_DATE_CUTOFF", "2030-01-01")

# ── Rule 7: ký tự vô hình cần phát hiện ──────────────────────────────────────
_INVISIBLE_CHARS = ("\ufeff", "\u200b", "\u00ad")  # BOM, zero-width space, soft-hyphen


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _has_invisible_chars(s: str) -> bool:
    """Rule 7 helper: phát hiện BOM và ký tự vô hình trong text."""
    return any(c in s for c in _INVISIBLE_CHARS)


def _normalize_whitespace(s: str) -> str:
    """Rule 9 helper: chuẩn hóa nhiều space/tab/newline liên tiếp thành 1 space."""
    return re.sub(r"[ \t\r\n]+", " ", s).strip()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Baseline (mở rộng theo narrative Day 10):
    1) Quarantine: doc_id không thuộc allowlist (export lạ / catalog sai).
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: chunk hr_leave_policy có effective_date < HR_LEAVE_MIN_DATE (đọc từ env, mặc định 2026-01-01).
    4) Quarantine: chunk_text rỗng hoặc effective_date rỗng sau chuẩn hoá.
    5) Loại trùng nội dung chunk_text (giữ bản đầu).
    6) Fix stale refund: policy_refund_v4 chứa '14 ngày làm việc' → 7 ngày.

    Rules mới (Sprint 2):
    7) Quarantine: chunk_text chứa BOM (\\ufeff) hoặc ký tự vô hình (\\u200b, \\u00ad).
       metric_impact: inject 1 row BOM → quarantine_records tăng 1.
    8) Quarantine: effective_date vượt FUTURE_DATE_CUTOFF (đọc từ env, mặc định 2030-01-01).
       metric_impact: inject row '2099-01-01' → quarantine_records tăng 1.
    9) Chuẩn hóa whitespace thừa trong chunk_text (tab/newline/nhiều space → 1 space).
       metric_impact: inject row có tab/newline thừa → cleaned text thay đổi, marker '[cleaned: whitespace_normalized]' xuất hiện.
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # Rule 1: allowlist doc_id
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # Rule 2: chuẩn hoá effective_date
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # Rule 3 (nâng cấp): HR cutoff đọc từ env thay vì hard-code (Distinction d)
        if doc_id == "hr_leave_policy" and eff_norm < HR_LEAVE_MIN_DATE:
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                    "hr_leave_min_date_used": HR_LEAVE_MIN_DATE,
                }
            )
            continue

        # Rule 4: chunk_text rỗng
        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # Rule 7 (mới): BOM và ký tự vô hình — quarantine trước khi dedup
        # Lý do quarantine thay vì strip: ký tự vô hình chỉ xuất hiện khi encoding sai ở nguồn,
        # nên phải trả về quarantine để team data source xử lý gốc rễ.
        if _has_invisible_chars(text):
            quarantine.append({**raw, "reason": "bom_or_invisible_char_in_text"})
            continue

        # Rule 9 (mới): chuẩn hóa whitespace thừa trước khi dedup và chunk_id
        ws_normalized = _normalize_whitespace(text)
        ws_changed = ws_normalized != text
        text = ws_normalized  # dùng bản đã normalize cho các bước tiếp theo

        # Rule 5: dedup theo nội dung đã chuẩn hóa
        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # Rule 8 (mới): effective_date vượt cutoff tương lai (đọc từ env)
        # Áp dụng sau parse thành công để so sánh chuỗi ISO chuẩn "YYYY-MM-DD".
        if eff_norm > FUTURE_DATE_CUTOFF:
            quarantine.append(
                {
                    **raw,
                    "reason": "effective_date_beyond_future_cutoff",
                    "effective_date_normalized": eff_norm,
                    "future_date_cutoff_used": FUTURE_DATE_CUTOFF,
                }
            )
            continue

        # Rule 6: fix stale refund window
        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        # Rule 9 marker: ghi nhận whitespace đã được chuẩn hóa
        if ws_changed and "[cleaned:" not in fixed_text:
            fixed_text += " [cleaned: whitespace_normalized]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
