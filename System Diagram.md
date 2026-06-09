```mermaid
C4Context
    title C4 Model - Level 2: Container Diagram cho supportLegalVn

    Person(user, "Người Dùng Cuối", "Luật sư, sinh viên luật, hoặc người dân cần tra cứu pháp lý.")

    System_Boundary(supportLegalVn, "supportLegalVn System") {
        Container(web_app, "Chat UI / Web Interface", "React / Next.js", "Giao diện cung cấp khung chat và kết quả tra cứu văn bản luật.")
        
        Container(api_gateway, "Backend API / Agentic Orchestrator", "Python / FastAPI (hoặc Node.js)", "Tiếp nhận câu hỏi, điều phối Agent, quyết định dùng tool nào và gọi LLM.")
        
        Container(embedding_service, "Embedding Pipeline", "Sentence Transformers", "Chunking văn bản và tạo Vector Embeddings từ dữ liệu đầu vào.")
        
        ContainerDb(qdrant_db, "Vector Database", "Qdrant", "Lưu trữ embeddings của tập dữ liệu 3.6GB phục vụ tìm kiếm ngữ nghĩa (Semantic Search).")
        
        ContainerDb(sqlite_db, "Metadata Database", "SQLite", "Lưu trữ metadata điều luật, lịch sử chat và các raw text đi kèm.")
    }

    System_Ext(llm_provider, "LLM Provider", "OpenAI / Claude / Local LLM", "Tạo sinh câu trả lời cuối cùng dựa trên context được cung cấp.")

    Rel(user, web_app, "Hỏi đáp & Tra cứu", "HTTPS")
    Rel(web_app, api_gateway, "Gửi query", "JSON/REST API")
    Rel(api_gateway, embedding_service, "Yêu cầu vector hóa query", "Internal Call")
    Rel(api_gateway, qdrant_db, "Truy vấn KNN/HNSW", "gRPC / REST")
    Rel(api_gateway, sqlite_db, "Lấy metadata & lịch sử", "SQL Queries")
    Rel(api_gateway, llm_provider, "Gửi Prompt + RAG Context", "API / HTTPS")
    Rel(embedding_service, qdrant_db, "Insert Vectors (Batch)", "gRPC")
    Rel(embedding_service, sqlite_db, "Insert Metadata", "SQL")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
