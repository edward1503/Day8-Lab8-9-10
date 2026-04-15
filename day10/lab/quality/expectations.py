"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.

Expectations mới (Sprint 2):
  E7 — no_bom_in_chunk_text (halt):
      Không chunk nào trong cleaned được chứa BOM (\\ufeff) hoặc zero-width space (\\u200b).
      severity=halt vì BOM gây sai lệch embedding (ký tự vô hình không bị vector space bỏ qua).
      metric_impact: nếu bỏ Rule 7 cleaning → E7 FAIL → pipeline halt; với Rule 7 hoạt động → E7 luôn PASS.
      Cross-check: E7 là lưới an toàn thứ 2 phía sau Rule 7 — nếu Rule 7 bị tắt/bypass, E7 vẫn bắt được.

  E8 — no_future_effective_date (warn):
      Không chunk nào trong cleaned có effective_date > FUTURE_DATE_CUTOFF (đọc từ env, mặc định 2030-01-01).
      severity=warn (không halt) vì có thể là pre-announcement policy hợp lệ.
      metric_impact: nếu bỏ Rule 8 cleaning + inject row '2099-01-01' → E8 WARN; với Rule 8 → E8 PASS.

  E9 — chunk_text_min_word_count (warn):
      Không chunk nào có ít hơn MIN_WORD_COUNT từ (mặc định 5 từ sau chuẩn hóa whitespace).
      severity=warn để không halt pipeline với edge case policy snippet ngắn.
      metric_impact: inject chunk '2 từ thôi' → E9 WARN; chunk chuẩn → E9 PASS.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# Đọc từ env để đồng bộ với cleaning_rules (không hard-code)
_FUTURE_DATE_CUTOFF: str = os.environ.get("FUTURE_DATE_CUTOFF", "2030-01-01")
_MIN_WORD_COUNT: int = int(os.environ.get("CHUNK_MIN_WORD_COUNT", "5"))
_INVISIBLE_CHARS = ("\ufeff", "\u200b", "\u00ad")


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # ── Expectations mới Sprint 2 ────────────────────────────────────────────

    # E7: không BOM / ký tự vô hình trong chunk_text (halt)
    # Cross-check với Rule 7: nếu cleaning bypass thì expectation này vẫn bắt được.
    # severity=halt vì BOM làm lệch embedding vector — retrieval sai không phát hiện được.
    bad_bom = [
        r
        for r in cleaned_rows
        if any(c in (r.get("chunk_text") or "") for c in _INVISIBLE_CHARS)
    ]
    ok7 = len(bad_bom) == 0
    results.append(
        ExpectationResult(
            "no_bom_or_invisible_char_in_cleaned",
            ok7,
            "halt",
            f"bom_violations={len(bad_bom)}",
        )
    )

    # E8: không effective_date nằm sau FUTURE_DATE_CUTOFF trong cleaned (warn)
    # severity=warn: pre-announcement policy hợp lệ có thể có ngày tương lai gần,
    # nhưng quá xa (>2030) thường là lỗi nhập liệu → báo warn để team xem xét.
    bad_future = [
        r
        for r in cleaned_rows
        if (r.get("effective_date") or "") > _FUTURE_DATE_CUTOFF
    ]
    ok8 = len(bad_future) == 0
    results.append(
        ExpectationResult(
            "no_future_effective_date_beyond_cutoff",
            ok8,
            "warn",
            f"future_date_violations={len(bad_future)} cutoff={_FUTURE_DATE_CUTOFF}",
        )
    )

    # E9: mỗi chunk_text có ít nhất MIN_WORD_COUNT từ (warn)
    # severity=warn: snippet policy ngắn có thể hợp lệ (vd tên section),
    # nhưng < 5 từ thường là artifact của chunking kém → cần review thủ công.
    short_words = [
        r
        for r in cleaned_rows
        if len((r.get("chunk_text") or "").split()) < _MIN_WORD_COUNT
    ]
    ok9 = len(short_words) == 0
    results.append(
        ExpectationResult(
            "chunk_text_min_word_count",
            ok9,
            "warn",
            f"short_chunks={len(short_words)} min_words={_MIN_WORD_COUNT}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
