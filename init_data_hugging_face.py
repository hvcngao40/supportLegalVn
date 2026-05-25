import os
import requests
import zipfile
from pathlib import Path
from tqdm import tqdm

# Cấu hình đường dẫn
DATA_DIR = Path("./sqlite_data")
# Thay bằng tên file thực tế của bạn sau khi giải nén (ví dụ: qdrant_storage hoặc legal.sqlite)
DB_FILE = DATA_DIR / "legal_poc.db"
# Link tải (Sau này bạn sẽ thay bằng link Raw của file zip trên Hugging Face)
DATASET_URL = "https://huggingface.co/datasets/hvcngao/legal-vn-rag/resolve/main/legal_poc.zip"
ZIP_PATH = DATA_DIR / "legal_poc.zip"


def download_large_file(url: str, dest_path: Path):
    """Tải file lớn với kỹ thuật streaming chunk để không ăn RAM"""
    response = requests.get(url, stream=True)
    response.raise_for_status()

    # Lấy tổng dung lượng file từ header
    total_size = int(response.headers.get('content-length', 0))
    block_size = 8192  # Tải từng chunk 8KB

    print(f"Bắt đầu tải khối dữ liệu RAG (Tổng: {total_size / (1024 ** 3):.2f} GB)...")
    print("Vui lòng giữ kết nối mạng. Quá trình này phụ thuộc vào tốc độ internet của bạn.")

    with open(dest_path, 'wb') as file, tqdm(
            desc=dest_path.name,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(block_size):
            size = file.write(data)
            bar.update(size)


def extract_and_cleanup(zip_path: Path, extract_to: Path):
    """Giải nén và xóa file gốc để tiết kiệm ổ cứng"""
    print(f"\nĐang giải nén dữ liệu vào {extract_to}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

    print("Giải nén hoàn tất. Đang dọn dẹp file tạm...")
    zip_path.unlink()  # Xóa file zip để trả lại 3.6GB trống cho ổ cứng người dùng


def init_database():
    """Hàm điều phối chính"""
    # 1. Kiểm tra nếu file đã có thì bỏ qua tải
    if DB_FILE.exists():
        print(f"✅ Hệ thống Vector/SQLite đã sẵn sàng tại '{DATA_DIR}'. Bỏ qua tải dữ liệu.")
        return

    # 2. Tạo thư mục nếu chưa có
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # 3. Tiến hành tải (nếu chưa tải dở)
        if not ZIP_PATH.exists():
            download_large_file(DATASET_URL, ZIP_PATH)
        else:
            print(f"Phát hiện file {ZIP_PATH.name} tải dở. Bắt đầu giải nén...")

        # 4. Giải nén và dọn dẹp
        extract_and_cleanup(ZIP_PATH, DATA_DIR)

        print("🚀 Khởi tạo hạ tầng dữ liệu thành công! Agent đã sẵn sàng đọc luật.")

    except Exception as e:
        print(f"❌ Lỗi trong quá trình khởi tạo dữ liệu: {e}")
        # Xóa file zip hỏng/tải lỗi để lần sau tải lại từ đầu
        if ZIP_PATH.exists():
            ZIP_PATH.unlink()


if __name__ == "__main__":
    init_database()