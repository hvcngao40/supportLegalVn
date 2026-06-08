# Kế hoạch triển khai: Viết file README hướng dẫn chạy local

Tài liệu này mô tả kế hoạch chi tiết để viết file `README.md` ở thư mục gốc của dự án, hướng dẫn người dùng chạy dự án **supportLegal** local từ đầu đến cuối.

## Mục tiêu
Tạo file `README.md` bằng tiếng Việt rõ ràng, mạch lạc, dễ hiểu và chuyên nghiệp giúp:
1. Thiết lập hạ tầng local bằng Docker (Qdrant, Redis, Postgres).
2. Cài đặt môi trường Python backend và Node.js frontend.
3. Cấu hình biến môi trường (`.env` cho backend, `.env.local` cho frontend).
4. Chạy crawler/indexer để nạp dữ liệu pháp luật.
5. Khởi chạy Backend API (FastAPI) và Frontend (Next.js).
6. Tích hợp hiển thị trực quan các ảnh kết quả từ thư mục `result/` để minh họa sinh động giao diện hệ thống.

## Nội dung chi tiết của README.md dự kiến

### 1. Giới thiệu chung và Kiến trúc hệ thống
- Tóm tắt mục tiêu của dự án **supportLegal** (Hệ thống RAG cho Pháp luật Việt Nam sử dụng cấu trúc trả lời IRAC).
- Sơ đồ/Giải thích kiến trúc Hybrid Search (Vector search + SQLite FTS5) kèm bộ phân loại chủ đề (Classifier).

### 2. Demo UI (Chèn ảnh từ thư mục `result/`)
- Nhúng các ảnh chụp màn hình trong thư mục `result/` bằng định dạng carousel/list để minh họa giao diện:
  - `result/1.png` - Giao diện trang chủ và tìm kiếm.
  - `result/2.png` - Câu trả lời từ RAG và cấu trúc IRAC.
  - `result/3.png` - Danh sách trích dẫn nguồn tài liệu tham chiếu.
  - `result/4.png` - Xem chi tiết nội dung gốc điều luật và highlight.
  - `result/5.png` - Lịch sử trò chuyện và các nhãn phân loại chủ đề.

### 3. Hướng dẫn chạy từng bước (Step-by-step)
- **Bước 1: Chạy hạ tầng (Docker)**
  - Hướng dẫn chạy `docker compose up -d` để khởi động Qdrant, Redis, Postgres.
- **Bước 2: Cài đặt và cấu hình Python backend**
  - Tạo virtualenv, kích hoạt và chạy `pip install -r requirements.txt`.
- **Bước 3: Cấu hình biến môi trường (`.env`)**
  - Tạo file `.env` từ `.env.example`.
  - Hướng dẫn cấu hình API Keys (Gemini, Groq, DeepSeek).
  - Cấu hình kết nối local Qdrant (`QDRANT_HOST=localhost`).
  - Hướng dẫn bật tắt LLM generation (`ENABLE_LLM_GENERATION=true`).
- **Bước 4: Chạy Indexer (Nạp dữ liệu)**
  - Chạy lệnh `python indexer.py` để lấy dữ liệu từ Hugging Face và lưu vào SQLite + Qdrant.
- **Bước 5: Chạy Backend API (FastAPI)**
  - Chạy `uvicorn app:app --host 0.0.0.0 --port 8000 --reload` hoặc `python app.py`.
- **Bước 6: Chạy Frontend (Next.js)**
  - Vào thư mục `frontend`, chạy `npm install`.
  - Tạo `frontend/.env.local` với cấu hình `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
  - Chạy `npm run dev`.

### 4. Chạy kiểm tra CLI
- Hướng dẫn chạy `python main.py` để test nhanh Hybrid Search trực tiếp trên CLI bằng dữ liệu mẫu.

### 5. Khắc phục sự cố thường gặp (Troubleshooting)
- Lỗi kết nối Qdrant.
- Lỗi SQLite database is locked.
- Lỗi API Rate limits (429).
