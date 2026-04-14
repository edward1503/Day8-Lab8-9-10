# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Đôn Đức  
**MSSV:** 2A202600145  
**Vai trò trong nhóm:** MCP Owner (Testing & Integration focus)  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Trong dự án này, tôi chịu trách nhiệm chính về việc **Đảm bảo tính ổn định và Triển khai (Integration & Deployment)** cho hạ tầng MCP. Trong khi thành viên khác tập trung vào kiến trúc lớp Transport, tôi tập trung vào việc làm thế nào để các Agent có thể kết nối và sử dụng các tool này một cách tin cậy nhất trong môi trường phân tán.

**Module/file tôi chịu trách nhiệm:**
- `instruction.md`: Xây dựng bộ tài liệu hướng dẫn vận hành toàn diện, quy định quy trình khởi động server và kết nối Client.
- `test_mcp_real.py`: Phát triển bộ integration test sử dụng `unittest` để kiểm tra kết nối end-to-end.
- `mcp_http_server.py`: Review và verify các endpoint health-check.
- `graph.py`: Thiết kế và triển khai bộ não điều phối (Supervisor) dựa trên LLM (GPT-4o-mini).
- `run_grading.py`: Chuẩn hóa format đầu ra của trace log đảm bảo tính minh bạch và khả năng truy vết (Traceability).

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Công việc của tôi đóng vai trò là "Quality Gate". Trước khi `Supervisor Owner` chạy các bộ test case lớn, tôi sử dụng `test_mcp_real.py` để verify rằng tầng hạ tầng đã sẵn sàng. Nếu không có phần của tôi, nhóm sẽ gặp rất nhiều lỗi "Connection Refused" giả mạo do Server chưa kịp khởi động hoặc sai CWD (Current Working Directory).

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Thiết kế cơ chế **Automated Health-Check với Polling & Retry** trong bộ Integration Test.

**Lý do:**
Khi triển khai MCP dưới dạng HTTP Server, một vấn đề thực tế là Agent và Server thường được khởi chạy gần như đồng thời. Do FastAPI cần vài giây để nạp model và expose port, Agent thường crash ngay lập tức nếu không tìm thấy server. Thay vì chỉ ghi chú "hãy đợi 5 giây" trong tài liệu, tôi quyết định implement logic tự động thăm dò trong `test_mcp_real.py`.

**Lựa chọn thay thế:** 
- **Option A:** Sử dụng lệnh `sleep` cứng trong bash script khởi động — không tối ưu vì thời gian khởi động model có thể thay đổi tùy cấu hình máy.
- **Option B (Chọn):** Implement logic retry-with-backoff. Script sẽ thử gọi endpoint `/health` tối đa 5 lần, mỗi lần cách nhau 2 giây. Nếu sau 10 giây vẫn không thấy server, nó mới báo lỗi chính xác.

**Bằng chứng từ code:**
```python
# Trong test_mcp_real.py
max_retries = 5
for i in range(max_retries):
    try:
        resp = requests.get("http://localhost:8000/health", timeout=2)
        if resp.status_code == 200:
            print("[OK] MCP Server reachable")
            return
    except Exception:
        print(f"Waiting for MCP server (retry {i+1})...")
        time.sleep(2)
```
Quyết định này giúp quy trình CI/CD và chấm bài của nhóm trở nên cực kỳ ổn định, loại bỏ hoàn toàn các lỗi race condition giữa các process.

**Quyết định 2: Kiến trúc Hybrid Orchestrator (LLM with Rule-based Fallback)**

**Lý do:**
Việc sử dụng LLM để điều phối (Supervisor) giúp hệ thống xử lý được các câu hỏi phức tạp (multi-hop) mà bộ rules keyword không thể bao quát hết. Tuy nhiên, phụ thuộc hoàn toàn vào LLM API là một rủi ro về availability (nếu hết quota hoặc mất mạng). Tôi quyết định triển khai một lớp bảo vệ: Supervisor sẽ ưu tiên dùng LLM, nhưng nếu có bất kỳ lỗi gì phát sinh, nó sẽ tự động fallback về bộ logic keyword cũ để đảm bảo Agent không bao giờ bị "treo".

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Lỗi **Tham chiếu Đường dẫn Tương đối (Relative Path Consistency)** của ChromaDB.

**Symptom:** 
Khi chạy `build_index.py` thì dữ liệu báo nạp thành công, nhưng khi chạy MCP Server hoặc Worker thì công cụ `search_kb` lại trả về kết quả rỗng (0 chunks), mặc dù terminal báo "Collection found".

**Root cause:** 
Lỗi nằm ở việc sử dụng đường dẫn tương đối `./chroma_db`. Khi MCP Server được chạy từ một terminal riêng (CWD khác) hoặc chạy qua script wrapper, Python sẽ coi vị trí thực thi là gốc. Kết quả là hệ thống tự khởi tạo một thư mục `chroma_db` trống tại vị trí mới thay vì trỏ vào thư mục đã có dữ liệu từ lab cũ.

**Cách sửa:** 
Tôi đã thực hiện hai việc:
1. Sửa logic nạp đường dẫn trong `mcp_server.py` và `retrieval.py` để ưu tiên sử dụng `os.path.abspath(__file__)` làm mốc tham chiếu nếu không tìm thấy biến môi trường.
2. Cập nhật `instruction.md` quy định nghiêm ngặt việc khởi chạy mọi component từ thư mục `/lab`.

**Bằng chứng trước/sau:** 
Trước khi sửa, `search_kb` qua HTTP trả về `total_found: 0`. Sau khi chuẩn hóa đường dẫn và verify qua `test_db_init.py`, kết quả trả về đúng 3 chunks liên quan đến SLA như kỳ vọng trong trace `run_20260414_163250`.

**Cải tiến 2: Thiết lập Safety Compliance cho các tác vụ High-Risk (HITL)**

**Vấn đề:** Ban đầu, hệ thống thiếu cơ chế dừng khi gặp tác vụ nhạy cảm hoặc rủi ro cao (như sự cố khẩn cấp lúc 2am).
**Cách giải quyết:** Tôi đã cài đặt một "chốt chặn bảo mật" trong `graph.py`. Khi Supervisor (LLM) phát hiện tín hiệu rủi ro cao, hệ thống sẽ thực thi lệnh **Force Hijack** — ép toàn bộ luồng xử lý phải dừng lại ở node `human_review` (HITL) để xin ý kiến người dùng. Điều này giúp hệ thống tuân thủ các quy tắc an toàn doanh nghiệp.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
Tôi làm tốt nhất ở khả năng **Documentation & Reliability**. Ngoài việc viết script test tự động, tôi còn nâng cấp hệ thống lên kiến trúc AI tin cậy (Reliable AI Integration) với khả năng fallback và an toàn (HITL). Điều này giúp sản phẩm không chỉ là một demo mà có khả năng vận hành thực tế.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Tôi chưa tối ưu hóa được phần bảo mật (Security). Hiện tại MCP HTTP server đang chạy công khai mà không có API Key, điều này có thể gây rủi ro rò rỉ dữ liệu `P1-LATEST` nếu server được expose ra ngoài mạng nội bộ.

**Nhóm phụ thuộc vào tôi ở đâu?**
Nhóm phụ thuộc vào tôi ở việc "Verify & Traceability". Tôi đã chuẩn hóa lại toàn bộ format JSONL để đảm bảo trace log chứa đầy đủ run_id, latency và bằng chứng trích dẫn, giúp quá trình hậu kiểm và chấm điểm diễn ra minh bạch.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ xây dựng một **Watcher Script** bằng Python để tự động quản lý các tiến trình. Đồng thời, tôi sẽ triển khai **Real-time HITL Notification** qua Slack. Thay vì chỉ in thông báo ra terminal, hệ thống sẽ gửi một tin nhắn kèm nút duyệt tới kênh quản lý, hoàn thiện vòng lặp phản hồi của Agent.

---
*File này lưu tại: `reports/individual/2A202600145-Nguyễn Đôn Đức.md`*
