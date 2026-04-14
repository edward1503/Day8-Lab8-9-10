"""
test_eval_trace.py — Sprint 4 tests for eval_trace.py

Run:
    python test_eval_trace.py
"""

import json
import tempfile
from pathlib import Path

from eval_trace import analyze_traces, compare_single_vs_multi


def _write_trace(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_analyze_traces_uses_latest_per_question():
    with tempfile.TemporaryDirectory() as td:
        traces_dir = Path(td)
        # Older trace for q01 (should be ignored).
        _write_trace(
            traces_dir / "old_q01.json",
            {
                "question_id": "q01",
                "supervisor_route": "retrieval_worker",
                "confidence": 0.2,
                "latency_ms": 1000,
                "mcp_tools_used": [],
                "hitl_triggered": False,
                "retrieved_sources": ["a.txt"],
            },
        )
        # Newer trace for q01 (should be used).
        _write_trace(
            traces_dir / "new_q01.json",
            {
                "question_id": "q01",
                "supervisor_route": "policy_tool_worker",
                "confidence": 0.8,
                "latency_ms": 3000,
                "mcp_tools_used": [{"tool": "search_kb"}],
                "hitl_triggered": False,
                "retrieved_sources": ["b.txt"],
            },
        )
        # Another question.
        _write_trace(
            traces_dir / "q02.json",
            {
                "question_id": "q02",
                "supervisor_route": "retrieval_worker",
                "confidence": 0.6,
                "latency_ms": 2000,
                "mcp_tools_used": [],
                "hitl_triggered": True,
                "retrieved_sources": ["b.txt"],
            },
        )

        metrics = analyze_traces(str(traces_dir))

        assert metrics["total_traces"] == 2
        assert metrics["routing_distribution"]["policy_tool_worker"].startswith("1/2")
        assert metrics["routing_distribution"]["retrieval_worker"].startswith("1/2")
        assert metrics["avg_confidence"] == 0.7
        assert metrics["avg_latency_ms"] == 2500
        assert metrics["mcp_usage_rate"].startswith("1/2")
        assert metrics["hitl_rate"].startswith("1/2")


def test_compare_single_vs_multi_with_baseline_file():
    with tempfile.TemporaryDirectory() as td:
        traces_dir = Path(td) / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        _write_trace(
            traces_dir / "q01.json",
            {
                "question_id": "q01",
                "supervisor_route": "retrieval_worker",
                "confidence": 0.5,
                "latency_ms": 1500,
                "mcp_tools_used": [],
                "hitl_triggered": False,
                "retrieved_sources": ["sla_p1_2026.txt"],
            },
        )

        baseline_path = Path(td) / "day08_baseline.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "total_questions": 15,
                    "avg_confidence": 0.4,
                    "avg_latency_ms": 1000,
                    "abstain_rate": "2/15 (13%)",
                    "multi_hop_accuracy": "1/2 (50%)",
                }
            ),
            encoding="utf-8",
        )

        comparison = compare_single_vs_multi(
            multi_traces_dir=str(traces_dir),
            day08_results_file=str(baseline_path),
        )
        assert comparison["day09_multi_agent"]["avg_confidence"] == 0.5
        assert comparison["analysis"]["confidence_delta"] == 0.1
        assert comparison["analysis"]["latency_delta_ms"] == 500


if __name__ == "__main__":
    test_analyze_traces_uses_latest_per_question()
    test_compare_single_vs_multi_with_baseline_file()
    print("All eval_trace tests passed.")
