#!/usr/bin/env python
"""
Redis Index Setup Script - Phase 19

This script initializes the Redis index with sample legal data from SQLite
and pre-populates it with embeddings for cache warm-up.

Usage:
    python scripts/redis_index_setup.py [--clear] [--sample-size 100]

Options:
    --clear: Clear existing Redis data before setup (use with caution)
    --sample-size: Number of articles to index (default: 100)
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.redis import RedisManager
from retrievers.qdrant_retriever import QdrantRetriever
from core.constants import SQLITE_PATH
import aiosqlite
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_sample_articles(db_path: str, limit: int = 100) -> list:
    """Retrieve sample articles from SQLite database."""
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT article_uuid, so_ky_hieu, article_title, full_content
                FROM legal_articles
                LIMIT ?
                """,
                (limit,)
            )
            rows = await cursor.fetchall()
            return [
                {
                    "article_uuid": row[0],
                    "so_ky_hieu": row[1],
                    "article_title": row[2],
                    "content": row[3][:500] if row[3] else "",  # Truncate for demo
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Failed to fetch articles: {e}")
        return []


async def index_articles(
    redis_mgr: RedisManager,
    qdrant_retriever: QdrantRetriever,
    articles: list
) -> int:
    """Index articles in Redis with embeddings."""
    indexed_count = 0
    
    for i, article in enumerate(articles):
        try:
            # Get embedding for article content
            embedding = await qdrant_retriever._embed_query(article["content"])
            if not embedding:
                logger.warning(f"Could not embed article {article['article_uuid']}")
                continue
            
            # Store in Redis
            snippet = article["content"][:200] + "..." if len(article["content"]) > 200 else article["content"]
            
            source = f"{article['so_ky_hieu']} - {article['article_title']}"
            
            doc_key = await redis_mgr.new_document(
                doc_id=article["article_uuid"],
                embedding=embedding,
                snippet=snippet,
                score=0.95,  # Demo score
                source=source,
                metadata={
                    "so_ky_hieu": article["so_ky_hieu"],
                    "article_title": article["article_title"],
                    "full_content": article["content"]
                }
            )
            
            indexed_count += 1
            if (i + 1) % 10 == 0:
                logger.info(f"Indexed {i + 1}/{len(articles)} articles")
            
        except Exception as e:
            logger.error(f"Failed to index article {article['article_uuid']}: {e}")
            continue
    
    return indexed_count


async def main():
    parser = argparse.ArgumentParser(description="Redis index setup for legal articles")
    parser.add_argument("--clear", action="store_true", help="Clear existing data")
    parser.add_argument("--sample-size", type=int, default=100, help="Number of articles to index")
    
    args = parser.parse_args()
    
    # Initialize managers
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_mgr = RedisManager(redis_url)
    
    try:
        # Connect to Redis
        logger.info(f"Connecting to Redis at {redis_url}...")
        await redis_mgr.init()
        logger.info("Redis connected successfully")
        
        # Clear if requested
        if args.clear:
            logger.warning("Clearing existing Redis data...")
            await redis_mgr.clear()
        
        # Get sample articles
        db_path = os.getenv("SQLITE_DB_PATH", SQLITE_PATH)
        logger.info(f"Loading sample articles from {db_path}...")
        articles = await get_sample_articles(db_path, args.sample_size)
        
        if not articles:
            logger.error("No articles found. Ensure SQLite database exists and has data.")
            return
        
        logger.info(f"Loaded {len(articles)} articles")
        
        # Initialize Qdrant retriever for embeddings
        logger.info("Initializing embedding model...")
        qdrant_retriever = QdrantRetriever()
        
        # Index articles
        logger.info(f"Indexing {len(articles)} articles into Redis...")
        indexed = await index_articles(redis_mgr, qdrant_retriever, articles)
        
        logger.info(f"✓ Successfully indexed {indexed}/{len(articles)} articles")
        
        # Test search
        logger.info("Testing vector search...")
        test_query = "bảo hiểm xã hội"
        test_embedding = await qdrant_retriever._embed_query(test_query)
        if test_embedding:
            results = await redis_mgr.vector_search("documents_idx", test_embedding, k=3, threshold=0.85)
            logger.info(f"Search for '{test_query}' returned {len(results)} results")
            for result in results:
                logger.info(f"  - {result.get('source', 'UNKNOWN')} (score: {result.get('score', 0):.2f})")
        
        logger.info("✓ Redis index setup completed successfully")
        
    except Exception as e:
        logger.error(f"Setup failed: {e}", exc_info=True)
        raise
    finally:
        await redis_mgr.close()


if __name__ == "__main__":
    asyncio.run(main())

