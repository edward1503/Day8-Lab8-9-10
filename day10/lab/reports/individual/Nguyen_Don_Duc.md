# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Đôn Đức  
**Vai trò:** Embed & Eval Owner  
**Ngày nộp:** 2026-04-15  

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

Tôi phụ trách toàn bộ hạ tầng lưu trữ vector và đo lường truy xuất (`Retrieval Evaluation`). Các module chính tôi thực hiện bao gồm:
- **`cmd_embed_internal` (trong `etl_pipeline.py`)**: Thiết lập `PersistentClient` của ChromaDB, cấu hình model `all-MiniLM-L6-v2` và quản lý Collection `day10_kb`.
- **`eval_retrieval.py`**: Xây dựng script query tự động, kiểm tra logic `contains_expected` và `hits_forbidden` dựa trên bộ câu hỏi Golden (`test_questions.json`).

Tôi đã trực tiếp thực hiện các lệnh nạp dữ liệu (clean vs injected) và xuất báo cáo đối chứng CSV để thẩm định độ hiệu quả của toàn bộ pipeline.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Quyết định quan trọng nhất của tôi là thiết lập tham số `top_k=3` kết hợp với logic **Aggregate Verification** trong script `eval_retrieval.py`. Thay vì chỉ kiểm tra chunk đứng đầu (`top-1`), tôi quyết định quét toàn bộ 3 kết quả trả về nhiều nhất để phát hiện "dữ liệu độc hại". 

Lý do là trong một số trường hợp, Model Embedding có thể ưu tiên các chunk "bẩn" (như chính sách 14 ngày cũ) lên vị trí top-2 hoặc top-3. Nếu chỉ kiểm top-1, hệ thống có thể báo PASS giả (False Negative), nhưng thực tế Agent vẫn có rủi ro đọc trúng dữ liệu sai ở các vị trí tiếp theo trong ngữ cảnh. Quyết định này giúp chỉ số `hits_forbidden` phản ánh chính xác độ sạch của toàn bộ không gian Vector chứ không chỉ là kết quả may rủi của Model.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Tôi đã xử lý lỗi "Vector Ghosts" (Vector bóng ma) phát sinh trong quá trình Embed run-id mới. Ban đầu, khi nạp dữ liệu từ `inject-bad` đè lên `clean-baseline`, các ID cũ không bị xóa mà vẫn tồn tại trong Collection nếu chúng không bị trùng ID. Điều này dẫn đến việc file `eval_injected.csv` cho kết quả hỗn loạn, trộn lẫn cả dữ liệu cũ và mới.

Tôi đã khắc phục bằng cách triển khai cơ chế **Pruning dựa trên Snapshot**. Tôi sử dụng `col.get(include=[])` để lấy toàn bộ ID hiện có trong DB, so sánh với tập ID mới từ file `cleaned.csv`, và thực hiện lệnh `col.delete(ids=drop)` cho những ID thừa. Việc này đảm bảo Collection luôn là một bản sao chính xác (Mirror) của dữ liệu vừa được Pipeline xử lý, đảm bảo tính **Idempotent** tuyệt đối cho hệ thống.

---

## 4. Bằng chứng trước / sau (80–120 từ)

Tôi đã trực tiếp chạy đánh giá và trích xuất dữ liệu từ `eval_clean.csv` và `eval_injected.csv` cho câu hỏi `q_refund_window`:

*   **Bản Inject (Run: `inject-bad`):** 
    - `hits_forbidden`: **yes** ✅ (Thành công trong việc phát hiện chunk 14 ngày lọt vào top-3).
*   **Bản Clean (Run: `clean-baseline`):**
    - `hits_forbidden`: **no** ✅ (Sau khi pipeline xử lý, không còn tìm thấy nội dung cấm).

Số liệu này chứng minh script `eval_retrieval.py` do tôi phát triển đã hoàn thành xuất sắc nhiệm vụ giám sát chất lượng Ingestion.

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ nâng cấp script `eval_retrieval.py` để tính toán thêm chỉ số **MRR (Mean Reciprocal Rank)**. Thay vì chỉ báo Yes/No, chỉ số này sẽ giúp tôi đánh giá xem các chunk "chuẩn" đang đứng ở vị trí nào. Nếu chunk đúng bị đẩy xuống top-3 thay vì top-1, tôi sẽ biết cần phải tinh chỉnh lại tham số của Model Embedding hoặc Re-ranker.

---
