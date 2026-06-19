from llama_index.llms.gemini import Gemini
from mcp.server.fastmcp import FastMCP

from core.classifier import LegalQueryClassifier
from core.rag_pipeline import LegalHybridRetriever, LegalRAGPipeline
from retrievers.qdrant_retriever import QdrantRetriever
from retrievers.sqlite_retriever import SQLiteFTS5Retriever

# Khởi tạo MCP Server
mcp_server = FastMCP("SupportLegalVn_MCP_Server")

classifier = LegalQueryClassifier()
v_retriever = QdrantRetriever()
f_retriever = SQLiteFTS5Retriever()

# Baseline: Vector only, no classifier
retriever = LegalHybridRetriever(
        classifier=classifier,
        vector_retriever=v_retriever,
        fts_retriever=f_retriever,
        vector_weight=1.0,
        keyword_weight=0.0,
        use_keyword=False,
        use_classifier=False
    )

llm = Gemini(model="models/gemini-2.0-flash")
pipeline = LegalRAGPipeline(retriever=retriever, llm=llm)


@mcp_server.tool()
async def search_legal_context(query: str, top_k: int = 5) -> str:
    """
    Tìm kiếm các điều luật, nghị định của Việt Nam phù hợp với tình huống người dùng.
    Sử dụng tool này đầu tiên khi người dùng hỏi về luật.
    """
    try:
        # Gọi xuống tầng DB (Qdrant + BM25) của bạn
        results = await pipeline.acustom_query(query=query)

        if not results:
            return "Không tìm thấy quy định pháp luật nào phù hợp với tình huống này."

        # Format kết quả trả về cho LLM dễ đọc
        formatted_context = "\n\n".join(
            f"--- BẮT ĐẦU TRÍCH ĐOẠN ---\n"
            f"Văn bản ID: {res.document_id}\n"
            f"Điều/Khoản: {res.article_name}\n"
            f"Nội dung: {res.content}\n"
            f"--- KẾT THÚC TRÍCH ĐOẠN ---"
            for res in results
        )
        return formatted_context
    except Exception as e:
        return f"Lỗi hệ thống khi tìm kiếm: {str(e)}"


@mcp_server.tool()
async def get_full_document(document_id: str) -> str:
    """
    Truy xuất toàn văn của một văn bản pháp luật khi cần đọc toàn bộ bối cảnh
    hoặc khi trích đoạn từ search_legal_context không đủ chi tiết.
    """
    try:
        # Gọi xuống tầng SQLite của bạn
        doc = await f_retriever.get_articles_by_uuids([document_id])

        if not doc:
            return f"Không tìm thấy văn bản nào với ID: {document_id}"

        return (
            f"Tên văn bản: {doc.text}\n"
        )
    except Exception as e:
        return f"Lỗi hệ thống khi truy xuất văn bản: {str(e)}"

if __name__ == "__main__":
    # Run server using the default standard I/O transport channel
    mcp_server.run(transport="sse")