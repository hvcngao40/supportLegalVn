import os
import json
import psycopg2
from psycopg2 import Error
from psycopg2.extras import execute_values
from datasets import load_dataset

# ================= CẤU HÌNH HỆ THỐNG =================
DB_CONFIG = {
    "host": "localhost",
    "user": "postgres",
    "password": "your_strong_password",
    "port": "5432"
}
DB_NAME = "support_legal_vn"
TABLE_NAME = "legal_articles"
STATE_FILE = "sync_state_postgres.json"
BATCH_SIZE = 1000  # Số lượng record insert mỗi lần


# ================= QUẢN LÝ TRẠNG THÁI =================
def get_last_processed_index():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            try:
                state = json.load(f)
                return state.get("last_index", 0)
            except json.JSONDecodeError:
                return 0
    return 0


def save_processed_index(index):
    with open(STATE_FILE, 'w') as f:
        json.dump({"last_index": index}, f)


# ================= KHỞI TẠO DATABASE & TABLE =================
def init_database():
    try:
        # Bước 1: Kết nối tới DB mặc định 'postgres' để kiểm tra & tạo DB mục tiêu
        conn = psycopg2.connect(dbname="postgres", **DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()

        # Kiểm tra nếu DB chưa tồn tại thì tạo mới
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}';")
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(f"CREATE DATABASE {DB_NAME};")
            print(f"✅ Đã tạo mới Database: {DB_NAME}")
        else:
            print(f"✅ Đã kiểm tra Database: {DB_NAME}")

        cursor.close()
        conn.close()

        # Bước 2: Kết nối trực tiếp vào Database mục tiêu để tạo bảng
        conn = psycopg2.connect(dbname=DB_NAME, **DB_CONFIG)
        cursor = conn.cursor()

        # Tạo bảng trong Postgres (Dùng TEXT thay cho MEDIUMTEXT)
        create_table_sql = f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    article_anchor VARCHAR(1000) PRIMARY KEY,
                    article_title TEXT NOT NULL,
                    topic_id VARCHAR(42),
                    topic_title VARCHAR(42),
                    subject_id VARCHAR(202),
                    subject_title TEXT,
                    chapter_title TEXT,
                    content_text TEXT NOT NULL,
                    source_note_text TEXT,
                    related_note_text TEXT,
                    source_url TEXT
                );
                """
        cursor.execute(create_table_sql)

        # Tạo Index nếu chưa có (Postgres dùng cú pháp riêng biệt cho INDEX)
        # cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_topic ON {TABLE_NAME} (topic_title);")

        conn.commit()
        print(f"✅ Đã kiểm tra/tạo bảng và index cho: {TABLE_NAME}")
        return conn, cursor

    except Error as e:
        print(f"❌ Lỗi cấu hình PostgreSQL: {e}")
        exit(1)


# ================= HÀM INSERT BATCH TỐI ƯU =================
def insert_batch_postgres(cursor, batch_data):
    # Sử dụng ON CONFLICT DO NOTHING để bỏ qua trùng lặp Primary Key một cách an toàn
    sql = f"""
        INSERT INTO {TABLE_NAME} (
            article_anchor, article_title, topic_id, topic_title, 
            subject_id, subject_title, chapter_title, content_text, 
            source_note_text, related_note_text, source_url
        ) VALUES %s 
        ON CONFLICT (article_anchor) DO NOTHING;
    """
    # execute_values nhanh hơn executemany của Postgres gấp 10 lần nhờ gộp các record vào 1 câu lệnh duy nhất
    execute_values(cursor, sql, batch_data)


# ================= HÀM CHÍNH =================
def main():
    conn, cursor = init_database()

    print("\n⏳ Đang tải dataset từ Hugging Face...")
    ds = load_dataset("tmquan/phapdien-moj-gov-vn", "articles", split="train")
    total_records = len(ds)
    print(f"✅ Tổng số bản ghi trong dataset: {total_records}")

    start_index = get_last_processed_index()
    if start_index > 0:
        print(f"🔄 Tiếp tục quá trình đồng bộ từ bản ghi thứ: {start_index}")

    batch = []

    try:
        for i in range(start_index, total_records):
            row = ds[i]

            # Xử lý bỏ kí tự '#' ở đầu chuỗi anchor
            anchor = str(row.get('article_anchor', '')).strip('#')
            if not anchor:
                print(f"⚠️ Bỏ qua bản ghi tại index {i} do thiếu article_anchor.")
                continue

            record = (
                anchor,
                row.get('article_title') or '',
                row.get('topic_id') or '',
                row.get('topic_title') or '',
                row.get('subject_id') or '',
                row.get('subject_title') or '',
                row.get('chapter_title') or '',
                row.get('content_text') or '',
                row.get('source_note_text') or '',
                row.get('related_note_text') or '',
                row.get('source_url') or ''
            )
            batch.append(record)

            # Khi batch đầy, thực hiện Insert
            if len(batch) >= BATCH_SIZE:
                insert_batch_postgres(cursor, batch)
                conn.commit()

                current_index = i + 1
                save_processed_index(current_index)
                batch = []  # Reset batch

                print(f"Tiến độ: Đã lưu {current_index}/{total_records} ({(current_index / total_records) * 100:.2f}%)")

        # Xử lý các dòng còn sót lại ở batch cuối
        if len(batch) > 0:
            insert_batch_postgres(cursor, batch)
            conn.commit()
            save_processed_index(total_records)
            print(f"Tiến độ: Đã lưu {total_records}/{total_records} (100%)")

        print("\n🎉 HOÀN THÀNH ĐỒNG BỘ DỮ LIỆU PHÁP ĐIỂN VÀO POSTGRESQL!")

    except Exception as e:
        print(f"\n⚠️ Đã xảy ra lỗi trong quá trình xử lý: {e}")
        print("Trạng thái tiến độ đã được lưu lại. Script sẽ tự chạy tiếp tục khi bạn kích hoạt lại.")
        conn.rollback()

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()