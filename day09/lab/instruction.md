# Hướng dẫn chạy dự án Day 09— Multi-Agent Orchestration

Dự án này triển khai hệ thống Multi-Agent theo mô hình **Supervisor-Worker** sử dụng **Model Context Protocol (MCP)** để quản lý các công cụ và khả năng bên ngoài.

## 1. Yêu cầu hệ thống
- Python 3.9 trở lên.
- Cài đặt các thư viện cần thiết:
  ```bash
  pip install -r requirements.txt
  ```

## 2. Cấu hình môi trường
1. Sao chép file mẫu `.env.example` thành `.env`:
   ```bash
   cp .env.example .env
   ```
2. Mở file `.env` và điền mã API của bạn:
   - `OPENAI_API_KEY`: Bắt buộc nếu sử dụng mô hình OpenAI.
   - `LANGSMITH_API_KEY`: Tùy chọn nếu muốn theo dõi trace trên LangSmith.

## 3. Khởi tạo dữ liệu (Indexing)
Trước khi chạy agent, bạn cần đưa các tài liệu vào cơ sở dữ liệu vector (ChromaDB):
```bash
python build_index.py
```
Lệnh này sẽ đọc các file trong `data/docs/` và lưu index vào thư mục `chroma_db/`.

## 4. Cách chạy dự án

### Cách 1: Chạy mô hình Local (Standard)
Đây là cách chạy thông thường, mọi thành phần chạy trong cùng một tiến trình:
```bash
python graph.py
```

### Cách 2: Chạy qua MCP HTTP Server (Advanced)
Sử dụng nếu bạn muốn triển khai MCP Server như một dịch vụ riêng biệt qua HTTP:

1. **Khởi động MCP Server:**
   ```bash
   python mcp_http_server.py
   ```
   Server sẽ chạy tại `http://localhost:8000`.

2. **Chạy Orchestrator kết nối qua HTTP:**
   - **Windows (PowerShell):**
     ```powershell
     $env:MCP_TRANSPORT="http"; $env:MCP_SERVER_URL="http://localhost:8000"; python graph.py
     ```
   - **Linux/macOS:**
     ```bash
     MCP_TRANSPORT=http MCP_SERVER_URL=http://localhost:8000 python graph.py
     ```

## 5. Kiểm tra và Đánh giá (Evaluation)
Để chạy kiểm tra tự động trên bộ câu hỏi mẫu và tạo file trace:
```bash
python eval_trace.py
```
Kết quả trace sẽ được lưu tại `artifacts/traces/`.

## 6. Cấu trúc thư mục quan trọng
- `graph.py`: Luồng điều phối chính (Supervisor).
- `workers/`: Chứa các agent chuyên biệt (Retrieval, Policy, Synthesis).
- `mcp_server.py`: Định nghĩa các công cụ (Tools) cho MCP.
- `mcp_http_server.py`: Server FastAPI để expose công cụ qua HTTP.
- `data/docs/`: Chứa các tài liệu hướng dẫn nội bộ.
- `contracts/`: Định nghĩa định dạng đầu vào/đầu ra của các Worker.
