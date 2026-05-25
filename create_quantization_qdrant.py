import os
import asyncio

from qdrant_client import models, AsyncQdrantClient


async def compress_collection(client):
    collection_name = "legal_articles"

    # Kiểm tra sự tồn tại của collection trước khi update
    print(f"Đang cấu hình nén cho: {collection_name}...")

    await client.update_collection(
        collection_name=collection_name,
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(
                type=models.ScalarType.INT8,
                always_ram=True,
            )
        )
    )
    print("✅ Đã gửi lệnh kích hoạt Scalar Quantization INT8 thành công.")
    print("⚠️  Lưu ý: Qdrant sẽ cần thời gian để nén 2.7 triệu vector ở background.")
    print("   Bạn hãy theo dõi trạng thái 'Green' trên Dashboard trước khi test tốc độ.")


async def main():
    # Sử dụng host/port phù hợp với cấu hình Docker của bạn
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))  # Thường là 6333 (HTTP) hoặc 6334 (gRPC)

    client = AsyncQdrantClient(
        host=host,
        port=port,
        prefer_grpc=True,
        check_compatibility=False,
    )

    try:
        await compress_collection(client)
    finally:
        await client.close()  # Đóng kết nối an toàn


if __name__ == "__main__":
    asyncio.run(main())