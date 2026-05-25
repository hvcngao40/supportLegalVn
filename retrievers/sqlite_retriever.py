import aiosqlite
import re
import time
import os
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional

from llama_index.core import QueryBundle
from llama_index.core.retrievers import BaseRetriever

from core.constants import SQLITE_PATH
from core.retrieval_types import RetrievalNode, make_retrieval_node
from db.sqlite import normalize_so_ky_hieu_key


class SQLiteFTS5Retriever(BaseRetriever):
    """
    SQLite helper retriever.

    New primary use:
    - BM25 search on article title (article-level candidates).
    - fetch chunks by article_uuid only for the legacy fallback.

    Legacy use:
    - chunk-level FTS5 search via chunks_fts.
    """

    def __init__(self, db_path: str = SQLITE_PATH, top_k: int = 50):
        self.db_path = db_path
        self.top_k = top_k
        self._article_fts_table: Optional[str] = None
        self._chunk_fts_table: Optional[str] = None
        self._so_ky_hieu_index_cache: Optional[dict[str, List[str]]] = None
        self._pool_size = max(1, int(os.getenv("SQLITE_POOL_SIZE", "4")))
        self._pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._pool_semaphore = asyncio.Semaphore(self._pool_size)
        super().__init__()

    @asynccontextmanager
    async def _get_db(self) -> aiosqlite.Connection:
        """Borrow a pooled SQLite connection to limit FD usage under load."""
        await self._pool_semaphore.acquire()
        conn: Optional[aiosqlite.Connection] = None
        try:
            async with self._pool_lock:
                if self._pool:
                    conn = self._pool.pop()
            if conn is None:
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
            yield conn
        finally:
            if conn is not None:
                async with self._pool_lock:
                    self._pool.append(conn)
            self._pool_semaphore.release()

    async def close(self) -> None:
        """Close pooled connections (best-effort)."""
        async with self._pool_lock:
            conns = list(self._pool)
            self._pool.clear()
        for conn in conns:
            try:
                await conn.close()
            except Exception:
                pass

    def _retrieve(self, query_bundle: QueryBundle) -> List[RetrievalNode]:
        """Synchronous retrieve (deprecated)."""
        return []

    def _sanitize_query(self, query_str: str) -> str:
        safe_query = re.sub(r"[^\w\sÀ-ỹ]", " ", query_str).strip()
        return safe_query or query_str.strip()

    async def _table_exists(self, db: aiosqlite.Connection, table_name: str) -> bool:
        async with db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (table_name,),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def _resolve_fts_table(
        self,
        db: aiosqlite.Connection,
        candidates: List[str],
        cache_attr: str,
    ) -> Optional[str]:
        cached = getattr(self, cache_attr)
        if cached:
            return cached

        for table_name in candidates:
            if await self._table_exists(db, table_name):
                setattr(self, cache_attr, table_name)
                return table_name

        return None

    async def _column_exists(self, db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
        async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
            rows = await cursor.fetchall()
            return any(row[1] == column_name for row in rows)

    async def _load_so_ky_hieu_index_cache(self, db: aiosqlite.Connection) -> dict[str, List[str]]:
        if self._so_ky_hieu_index_cache is not None:
            return self._so_ky_hieu_index_cache

        index_map: dict[str, List[str]] = {}
        async with db.execute(
            "SELECT DISTINCT so_ky_hieu FROM legal_articles WHERE so_ky_hieu IS NOT NULL AND so_ky_hieu != ''"
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            raw = row[0]
            norm = normalize_so_ky_hieu_key(raw)
            if not norm:
                continue
            index_map.setdefault(norm, []).append(raw)
            index_map.setdefault(raw.strip(), []).append(raw)

        self._so_ky_hieu_index_cache = index_map
        return index_map

    async def _aretrieve(self, query_bundle: QueryBundle) -> List[RetrievalNode]:
        """Legacy chunk-level search using FTS5."""
        query_str = query_bundle.query_str
        safe_query = self._sanitize_query(query_str)

        nodes: List[RetrievalNode] = []
        try:
            async with self._get_db() as db:
                db.row_factory = aiosqlite.Row
                chunk_table = await self._resolve_fts_table(
                    db,
                    candidates=["chunks_fts"],
                    cache_attr="_chunk_fts_table",
                )
                if not chunk_table:
                    return []

                sql = f"""
                    SELECT 
                        lc.chunk_id,
                        lc.article_uuid,
                        lc.doc_id,
                        lc.so_ky_hieu,
                        lc.chunk_path,
                        lc.content,
                        -bm25({chunk_table}) AS score
                    FROM {chunk_table} fts
                    JOIN legal_chunks lc ON lc.chunk_id = fts.chunk_id
                    WHERE {chunk_table} MATCH ?
                    ORDER BY score DESC
                    LIMIT ?
                """

                async with db.execute(sql, (safe_query, self.top_k)) as cursor:
                    rows = await cursor.fetchall()

                    for row in rows:
                        metadata = {
                            "chunk_id": row["chunk_id"],
                            "article_uuid": row["article_uuid"],
                            "doc_id": row["doc_id"],
                            "so_ky_hieu": row["so_ky_hieu"],
                            "chunk_path": row["chunk_path"],
                            "type": "CHUNK",
                        }
                        nodes.append(
                            make_retrieval_node(
                                node_id=row["chunk_id"],
                                text=row["content"],
                                metadata=metadata,
                                score=float(row["score"]),
                            )
                        )
        except Exception as e:
            print(f"[Error] SQLite FTS5 retrieval failed: {e}")

        return nodes

    async def aretrieve(self, query_str: str) -> List[RetrievalNode]:
        """Convenience wrapper for legacy FTS5 chunk search."""
        return await self._aretrieve(QueryBundle(query_str))

    async def aretrieve_articles_by_title(
        self,
        query_str: str,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> List[RetrievalNode]:
        """
        Primary keyword path for article candidates.

        This expects an FTS5 table that indexes article titles and stores article_uuid.
        Common table name used by the indexer: `article_titles_fts`.
        """
        safe_query = self._sanitize_query(query_str)
        limit = top_k or self.top_k

        nodes: List[RetrievalNode] = []
        start_time = time.time()
        try:
            async with self._get_db() as db:
                db.row_factory = aiosqlite.Row
                article_table = await self._resolve_fts_table(
                    db,
                    candidates=[
                        "article_titles_fts",
                        "article_title_fts",
                        "legal_article_titles_fts",
                        "articles_title_fts",
                        "articles_fts",
                    ],
                    cache_attr="_article_fts_table",
                )
                if not article_table:
                    return []

                sql = f"""
                    SELECT
                        la.article_uuid,
                        la.doc_id,
                        la.so_ky_hieu,
                        la.article_title,
                        la.article_path,
                        -bm25({article_table}) AS score
                    FROM {article_table} fts
                    JOIN legal_articles la ON la.article_uuid = fts.article_uuid
                    WHERE {article_table} MATCH ?
                """
                params = [safe_query]
                
                if doc_type:
                    doc_type_lower = doc_type.lower()
                    if "luật" in doc_type_lower:
                        sql += " AND la.so_ky_hieu LIKE '%Luật%'"
                    elif "nghị định" in doc_type_lower:
                        sql += " AND la.so_ky_hieu LIKE '%NĐ-CP%'"
                    elif "thông tư" in doc_type_lower:
                        sql += " AND la.so_ky_hieu LIKE '%TT-%'"
                    else:
                        sql += " AND la.so_ky_hieu LIKE ?"
                        params.append(f"%{doc_type}%")

                sql += """
                    ORDER BY score DESC
                    LIMIT ?
                """
                params.append(limit)

                async with db.execute(sql, tuple(params)) as cursor:
                    rows = await cursor.fetchall()

                    for row in rows:
                        metadata = {
                            "article_uuid": row["article_uuid"],
                            "doc_id": row["doc_id"],
                            "so_ky_hieu": row["so_ky_hieu"],
                            "article_title": row["article_title"],
                            "article_path": row["article_path"],
                            "type": "ARTICLE",
                        }
                        nodes.append(
                            make_retrieval_node(
                                node_id=row["article_uuid"],
                                # Candidate stage is metadata-only; full content is hydrated later.
                                text=row["article_title"] or row["so_ky_hieu"] or "",
                                metadata=metadata,
                                score=float(row["score"]),
                            )
                        )
        except Exception as e:
            print(f"[Error] SQLite article title BM25 retrieval failed: {e}")

        print(
            "[SQLiteFTS5Retriever] Title BM25 took "
            f"{time.time() - start_time:.2f}s, hits: {len(nodes)}"
        )
        return nodes

    async def aretrieve_articles_by_so_ky_hieu(
        self,
        query_str: str,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> List[RetrievalNode]:
        """
        Search canonical articles by document identifier (`so_ky_hieu`) only.

        Uses raw exact match first, then a normalized match against
        `so_ky_hieu_norm` when that column exists.
        """
        exact_query = query_str.strip()
        normalized_query = normalize_so_ky_hieu_key(query_str)
        limit = top_k or self.top_k

        nodes: List[RetrievalNode] = []
        start_time = time.time()
        try:
            async with self._get_db() as db:
                db.row_factory = aiosqlite.Row

                index_map = await self._load_so_ky_hieu_index_cache(db)
                raw_values = []
                for key in (exact_query, normalized_query):
                    if key and key in index_map:
                        raw_values.extend(index_map[key])
                # Deduplicate while preserving order
                seen_raw = set()
                raw_values = [rv for rv in raw_values if rv and not (rv in seen_raw or seen_raw.add(rv))]

                if raw_values:
                    placeholders = ",".join("?" * len(raw_values))
                    sql = f"""
                        SELECT
                            article_uuid,
                            doc_id,
                            so_ky_hieu,
                            article_title,
                            article_path,
                            so_ky_hieu_norm,
                            1.0 AS score
                        FROM legal_articles la
                        WHERE la.so_ky_hieu IN ({placeholders})
                    """
                    params = raw_values
                else:
                    has_norm_column = await self._column_exists(db, "legal_articles", "so_ky_hieu_norm")

                    if has_norm_column:
                        sql = """
                            SELECT
                                article_uuid,
                                doc_id,
                                so_ky_hieu,
                                article_title,
                                article_path,
                                so_ky_hieu_norm,
                                1.0 AS score
                            FROM legal_articles la
                            WHERE la.so_ky_hieu = ?
                               OR la.so_ky_hieu_norm = ?
                               OR lower(replace(replace(replace(la.so_ky_hieu, '/', ' '), '-', ' '), '_', ' ')) = ?
                        """
                        params = [exact_query, normalized_query, normalized_query]
                    else:
                        sql = """
                            SELECT
                                article_uuid,
                                doc_id,
                                so_ky_hieu,
                                article_title,
                                article_path,
                                NULL AS so_ky_hieu_norm,
                                1.0 AS score
                            FROM legal_articles la
                            WHERE la.so_ky_hieu = ?
                               OR lower(replace(replace(replace(la.so_ky_hieu, '/', ' '), '-', ' '), '_', ' ')) = ?
                        """
                        params = [exact_query, normalized_query]

                if doc_type:
                    doc_type_lower = doc_type.lower()
                    if "luật" in doc_type_lower:
                        sql += " AND la.so_ky_hieu LIKE '%Luật%'"
                    elif "nghị định" in doc_type_lower:
                        sql += " AND la.so_ky_hieu LIKE '%NĐ-CP%'"
                    elif "thông tư" in doc_type_lower:
                        sql += " AND la.so_ky_hieu LIKE '%TT-%'"
                    else:
                        sql += " AND la.so_ky_hieu LIKE ?"
                        params.append(f"%{doc_type}%")

                sql += "\n                    LIMIT ?\n                "
                params.append(limit)

                async with db.execute(sql, tuple(params)) as cursor:
                    rows = await cursor.fetchall()

                    for row in rows:
                        metadata = {
                            "article_uuid": row["article_uuid"],
                            "doc_id": row["doc_id"],
                            "so_ky_hieu": row["so_ky_hieu"],
                            "so_ky_hieu_norm": row["so_ky_hieu_norm"],
                            "article_title": row["article_title"],
                            "article_path": row["article_path"],
                            "type": "ARTICLE",
                        }
                        nodes.append(
                            make_retrieval_node(
                                node_id=row["article_uuid"],
                                text=row["article_title"] or row["so_ky_hieu"] or "",
                                metadata=metadata,
                                score=float(row["score"]),
                            )
                        )
        except Exception as e:
            print(f"[Error] SQLite article identifier retrieval failed: {e}")

        print(
            "[SQLiteFTS5Retriever] so_ky_hieu search took "
            f"{time.time() - start_time:.2f}s, hits: {len(nodes)}"
        )
        return nodes

    async def aretrieve_articles_by_identifier(
        self,
        query_str: str,
        top_k: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> List[RetrievalNode]:
        """Backward-compatible alias for so_ky_hieu search."""
        return await self.aretrieve_articles_by_so_ky_hieu(
            query_str,
            top_k=top_k,
            doc_type=doc_type,
        )

    async def get_chunks_by_articles(
        self,
        article_uuids: List[str],
        limit: Optional[int] = 200,
    ) -> List[RetrievalNode]:
        """
        Fetch chunks that belong to the given list of article UUIDs.

        Used only by the legacy fallback.
        """
        if not article_uuids:
            return []

        seen = set()
        unique_article_uuids = []
        for aid in article_uuids:
            if aid and aid not in seen:
                seen.add(aid)
                unique_article_uuids.append(aid)

        if not unique_article_uuids:
            return []

        placeholders = ",".join("?" * len(unique_article_uuids))
        sql = f"""
            SELECT
                chunk_id,
                article_uuid,
                doc_id,
                so_ky_hieu,
                chunk_path,
                content
            FROM legal_chunks
            WHERE article_uuid IN ({placeholders})
            ORDER BY article_uuid, chunk_path, chunk_id
        """
        if limit is not None:
            sql += " LIMIT ?"

        nodes: List[RetrievalNode] = []
        try:
            async with self._get_db() as db:
                db.row_factory = aiosqlite.Row
                params = tuple(unique_article_uuids)
                if limit is not None:
                    params = params + (limit,)

                async with db.execute(sql, params) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        metadata = {
                            "chunk_id": row["chunk_id"],
                            "article_uuid": row["article_uuid"],
                            "doc_id": row["doc_id"],
                            "so_ky_hieu": row["so_ky_hieu"],
                            "chunk_path": row["chunk_path"],
                            "type": "CHUNK",
                        }
                        nodes.append(
                            make_retrieval_node(
                                node_id=row["chunk_id"],
                                text=row["content"],
                                metadata=metadata,
                                score=1.0,
                            )
                        )
        except Exception as e:
            print(f"[Error] SQLite chunk fetch by article_uuid failed: {e}")

        return nodes

    async def get_articles_by_uuids(self, article_uuids: List[str]) -> List[RetrievalNode]:
        """
        Fetch canonical article rows from SQLite.
        """
        if not article_uuids:
            return []

        seen = set()
        unique_article_uuids = []
        for aid in article_uuids:
            if aid and aid not in seen:
                seen.add(aid)
                unique_article_uuids.append(aid)

        if not unique_article_uuids:
            return []

        placeholders = ",".join("?" * len(unique_article_uuids))
        sql = f"""
            SELECT
                article_uuid,
                doc_id,
                so_ky_hieu,
                so_ky_hieu_norm,
                article_title,
                article_path,
                full_content
            FROM legal_articles
            WHERE article_uuid IN ({placeholders})
        """

        nodes: List[RetrievalNode] = []
        try:
            async with self._get_db() as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(sql, tuple(unique_article_uuids)) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        metadata = {
                            "article_uuid": row["article_uuid"],
                            "doc_id": row["doc_id"],
                            "so_ky_hieu": row["so_ky_hieu"],
                            "so_ky_hieu_norm": row["so_ky_hieu_norm"],
                            "article_title": row["article_title"],
                            "article_path": row["article_path"],
                            "type": "ARTICLE",
                        }
                        nodes.append(
                            make_retrieval_node(
                                node_id=row["article_uuid"],
                                text=row["full_content"] or "",
                                metadata=metadata,
                                score=1.0,
                            )
                        )
        except Exception as e:
            print(f"[Error] SQLite article fetch failed: {e}")

        return nodes
