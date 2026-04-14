# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Vu Quang Phuc  
**MSSV:** 2A202600346  
**Vai trò trong nhóm:** Trace & Docs Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `eval_trace.py`
- Functions tôi implement: `run_test_questions()`, `analyze_traces()`, `compare_single_vs_multi()`, `save_eval_report()`

Trong Sprint 4, tôi chịu trách nhiệm phần đánh giá và tài liệu hóa kết quả chạy pipeline. Tôi tập trung vào việc chạy bộ 15 câu hỏi test, chuẩn hóa trace output, và tổng hợp metrics để nhóm có thể nhìn thấy routing distribution, confidence, latency, mức sử dụng MCP, và tỉ lệ HITL. Ngoài phần code, tôi điền hai tài liệu bắt buộc trong `docs/`: `routing_decisions.md` và `single_vs_multi_comparison.md` dựa trên trace thật thay vì ghi mô tả chung chung. Tôi cũng bổ sung test riêng cho Sprint 4 là `test_eval_trace.py` để kiểm tra logic phân tích trace và so sánh Day08/Day09.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Phần của tôi phụ thuộc trực tiếp vào output từ `graph.py` và các worker vì nếu trace không đúng format thì không thể phân tích. Ngược lại, kết quả trong `eval_report.json` và các docs do tôi làm là đầu vào để cả nhóm review chất lượng routing và thảo luận cải tiến cho Sprint sau.

**Bằng chứng:**

- `artifacts/traces/run_20260414_161103.json` (q03), `run_20260414_161131.json` (q09), `run_20260414_161207.json` (q15)
- `artifacts/eval_report.json`
- `docs/routing_decisions.md`, `docs/single_vs_multi_comparison.md`
- `test_eval_trace.py`

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Trong `analyze_traces()`, chỉ lấy **latest trace theo từng `question_id`** thay vì cộng tất cả file trong `artifacts/traces/`.

Lúc đầu, nếu cộng toàn bộ trace thì metrics bị méo vì trong thư mục có nhiều lần chạy lặp lại (debug runs). Ví dụ cùng một câu hỏi có thể xuất hiện nhiều file khác nhau, khiến `routing_distribution` và `avg_latency` phản ánh lịch sử debug chứ không phản ánh kết quả evaluation chính thức 15 câu. Tôi cân nhắc hai cách:

1. Xóa thủ công trace cũ trước mỗi lần chạy.
2. Viết loader tự động deduplicate theo `question_id` và ưu tiên file mới nhất.

Tôi chọn cách 2 vì ổn định hơn, không phụ thuộc thao tác tay và giúp chạy lại nhiều lần vẫn giữ báo cáo đúng logic Sprint 4. Quyết định này giúp metrics nhất quán: `total_traces=15`, `routing_accuracy=15/15`, phân phối route rõ ràng 9 retrieval / 6 policy.

**Trade-off đã chấp nhận:**

Mất thông tin lịch sử các lần chạy cũ trong báo cáo tổng hợp mặc định. Tuy nhiên, dữ liệu cũ vẫn còn trong file trace để debug thủ công khi cần.

**Bằng chứng từ trace/code:**

```python
def _load_traces(traces_dir: str, latest_per_question: bool = True) -> list:
    trace_files = sorted(trace_files, key=os.path.getmtime, reverse=True)
    seen_question_ids = set()
    for fpath in trace_files:
        trace = json.load(f)
        qid = trace.get("question_id")
        if latest_per_question and qid:
            if qid in seen_question_ids:
                continue
            seen_question_ids.add(qid)
        traces.append(trace)
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** `compare_single_vs_multi()` để placeholder TODO nên `eval_report.json` luôn có baseline Day08 giả (`avg_confidence=0`, `avg_latency_ms=0`) và không có delta thực tế.

**Symptom (pipeline làm gì sai?):**

Khi chạy `python eval_trace.py --compare`, file `artifacts/eval_report.json` được tạo nhưng phần comparison không dùng được cho báo cáo vì giá trị Day08 là hardcode và các trường delta vẫn ghi TODO.

**Root cause:**

Trong code cũ, function so sánh chưa có loader baseline thực, chưa parse được dữ liệu Day08, và không tính delta từ dữ liệu đã có.

**Cách sửa:**

Tôi bổ sung `_load_day08_baseline()` để:
- Ưu tiên đọc file JSON baseline nếu truyền qua CLI `--day08-baseline`
- Nếu không có, fallback sang đọc `day08/lab/results/scorecard_baseline.md` và lấy Faithfulness làm confidence proxy
- Trả về cấu trúc N/A rõ ràng nếu thiếu dữ liệu

Sau đó tôi cập nhật `compare_single_vs_multi()` để tính `confidence_delta` và `latency_delta_ms` thay vì để TODO.

**Bằng chứng trước/sau:**

- Trước sửa: `analysis.latency_delta = "TODO..."`, `analysis.accuracy_delta = "TODO..."`
- Sau sửa: `analysis.latency_delta_ms` và `analysis.confidence_delta` có giá trị tính toán hoặc `N/A` có giải thích.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**

Tôi làm tốt phần biến trace thành dữ liệu có thể đọc và quyết định được. Thay vì chỉ chạy script cho có output, tôi chuẩn hóa logic để kết quả bám theo 15 câu đánh giá thực tế, đồng thời ghi rõ điểm mạnh/yếu của hệ thống trong docs.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Tôi chưa tự động hóa đầy đủ phần accuracy scoring theo expected answer. Hiện tại tôi mới tổng hợp metrics vận hành (route/confidence/latency/MCP/HITL), còn quality scoring chi tiết vẫn cần thêm judge hoặc rubric rõ hơn.

**Nhóm phụ thuộc vào tôi ở đâu?**

Nhóm phụ thuộc vào phần tôi để có số liệu chính thức cho Sprint 4 (routing decisions + single vs multi comparison) và để chứng minh hệ thống hoạt động end-to-end.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi phụ thuộc vào output chuẩn từ `graph.py` và workers; nếu trace schema không ổn định thì phần phân tích và báo cáo của tôi sẽ sai hoặc không chạy được.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ thêm module chấm tự động theo expected fields (đặc biệt cho multi-hop `q13`, `q15` và abstain `q09`) để có thêm metrics “answer correctness by category”. Lý do: trace hiện đã đủ metadata route/workers, nhưng comparison vẫn thiếu lớp đo chất lượng nội dung nhất quán giữa các lần chạy. Nếu có scorer tự động, nhóm sẽ biết chính xác route nào tốt về cả vận hành lẫn chất lượng answer.

---

*File này lưu tại: `reports/individual/vu_quang_phuc.md`*
