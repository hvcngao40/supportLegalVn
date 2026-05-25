import numpy as np
import logging
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger(__name__)


async def warm_up_qdrant(client: AsyncQdrantClient, collection_name: str, dimension: int = 768):
    """
    Thực hiện vài query giả để ép Qdrant load index vào RAM.
    """
    logger.info(f"🚀 Bắt đầu Warm-up Qdrant cho collection: {collection_name}...")

    try:
        # Tạo 3 vector ngẫu nhiên (chỉ cần vector hợp lệ để Qdrant chạy engine tìm kiếm)
        dummy_vectors = np.random.rand(3, dimension).tolist()

        for i, vec in enumerate(dummy_vectors):
            await client.query_points(
                collection_name="legal_articles",
                using="dense",
                query=qmodels.NearestQuery(nearest=vec),  # Ăn HNSW Index
            )
            logger.info(f"   Query Warm-up thứ {i + 1} hoàn tất.")

        logger.info("✅ Warm-up hoàn thành! Index đã được nạp vào RAM.")
    except Exception as e:
        logger.error(f"❌ Warm-up Qdrant thất bại: {e}")