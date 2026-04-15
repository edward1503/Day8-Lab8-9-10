# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Đôn Đức
**ID:** 2A202600145  
**Vai trò:** Embed & Eval Owner (Vận hành & Kiểm soát chất lượng)  
**Ngày nộp:** 2026-04-15  

---

## 1. Tôi phụ trách phần nào? (~110 từ)

Trong dự án lần này, tôi chịu trách nhiệm chính ở giai đoạn **Vận hành (Operation)** và **Kiểm thử chất lượng (Quality Evaluation)**. Công việc cụ thể bao gồm:

- Thực thi `etl_pipeline.py` cho kịch bản **inject** (`run_id=inject-bad`, flag `--no-refund-fix --skip-validate`) và kịch bản **clean** (`run_id=clean-baseline`).
- Vận hành `eval_retrieval.py` để sinh `artifacts/eval/eval_injected.csv` (trạng thái xấu) và `artifacts/eval/eval_clean.csv` (trạng thái sạch).
- Đối chiếu hai file CSV để xác nhận cột `hits_forbidden` chuyển từ `yes` → `no` và `top1_doc_expected` của `q_leave_version` giữ nguyên `yes`.
- Phân tích kết quả và hoàn thiện `docs/quality_report.md` làm bằng chứng Sprint 3.

Tôi đóng vai trò chốt chặn cuối cùng xác nhận dữ liệu đủ điều kiện để agent truy xuất.

**Bằng chứng:** `artifacts/manifests/manifest_inject-bad.json`, `artifacts/manifests/manifest_clean-baseline.json`, `artifacts/eval/eval_injected.csv`, `artifacts/eval/eval_clean.csv`.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Quyết định kỹ thuật quan trọng nhất của tôi là lựa chọn **Chiến lược Đối chứng (Differential Testing)** giữa hai phiên bản `clean-baseline` và `inject-bad`. 

Thay vì chỉ kiểm tra xem hệ thống có chạy được không, tôi đã chủ động yêu cầu chạy pipeline với cờ `--no-refund-fix` kết hợp với `--skip-validate`. Quyết định sử dụng flag `--skip-validate` là cực kỳ quan trọng vì nó cho phép tôi "ép" dữ liệu lỗi vào hệ thống (mặc dù Expectation đã báo FAIL). Mục đích của việc này là để có được bộ dữ liệu "bẩn" làm bằng chứng đối chiếu trong file `eval_injected.csv`. Nếu không có quyết định này, chúng ta sẽ không có số liệu thực tế để chứng minh rủi ro cho giảng viên thấy Agent sẽ trả lời sai thế nào nếu thiếu các rule làm sạch.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Trong quá trình vận hành Sprint 3, tôi phát hiện một **Sự cố Chất lượng (Quality Anomaly)**: Dữ liệu "14 ngày hoàn tiền" cũ vẫn xuất hiện trong kết quả truy xuất dù chúng ta đang làm việc với chính sách v4 (7 ngày).

Thông qua việc phân tích log pipeline, tôi nhận thấy Expectation `refund_no_stale_14d_window` báo đỏ nhưng pipeline vẫn ghi nhận `PIPELINE_OK` (do đang chạy mode demo). Tôi đã kịp thời ghi nhận Anomaly này vào báo cáo Quality Report, chỉ ra rằng nếu không có cơ chế `halt` của pipeline, dữ liệu sai lệch này sẽ trực tiếp làm hỏng câu trả lời của Agent. Việc phát hiện kịp thời thông qua script `eval_retrieval.py` đã giúp team nhận ra tầm quan trọng của việc không được bypass các bước validate trong môi trường chính thức.

---

## 4. Bằng chứng trước / sau (80–120 từ)

Bằng chứng thực tế tôi thu thập được từ hai lần chạy máy:

- **Lần 1 (Bị inject lỗi - `inject-bad`):** Cột `hits_forbidden` báo **yes**. Agent tìm thấy thông tin sai lệch "14 ngày".
- **Lần 2 (Chạy chuẩn - `clean-baseline`):** Cột `hits_forbidden` báo **no**. Thông tin lỗi đã bị triệt tiêu hoàn toàn.

Dữ liệu này được tôi trích xuất trực tiếp từ các file `artifacts/eval/eval_clean.csv` và `eval_injected.csv` để làm bằng chứng cho báo cáo nhóm.

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ xây dựng một script nhỏ để **Tự động so sánh (Auto-diff)** giữa hai file CSV kết quả Eval. Hiện tại tôi đang phải đối chiếu thủ công bằng mắt, việc tự động hóa sẽ giúp phát hiện nhanh các thay đổi về `top1_doc_id` khi dữ liệu nguồn được cập nhật hàng ngày, giúp việc kiểm soát chất lượng (QA) trở nên chuyên nghiệp hơn.

---
