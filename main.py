# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import Response
from mcp_server import SseServerTransport
from mcp_server import mcp_server

app = FastAPI(title="Support Legal VN API")

# Khởi tạo SSE Transport layer của MCP
# Định nghĩa endpoint mà các LLM Client sẽ kết nối tới để gửi lệnh (Client -> Server)
sse_transport = SseServerTransport("/api/mcp/messages")

# Endpoint 1: Luồng phát dữ liệu (Server-Sent Events)
# LLM Client (như Cursor/Claude) sẽ kết nối vào đây và giữ kết nối mở để "nghe" phản hồi từ Server
@app.get("/api/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        # Cho phép MCP Server handle luồng đọc/ghi dữ liệu này
        await mcp_server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=mcp_server.create_initialization_options()
        )

# Endpoint 2: Luồng nhận dữ liệu (HTTP POST)
# Khi LLM Client muốn gọi tool (ví dụ: search_legal_context), nó sẽ POST dữ liệu JSON vào đây
@app.post("/api/mcp/messages")
async def mcp_messages_endpoint(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return Response(status_code=202)


# --- CÁC API REST CŨ CỦA BẠN VẪN CHẠY BÌNH THƯỜNG Ở ĐÂY ---
@app.get("/")
def read_root():
    return {"message": "Welcome to Support Legal VN System"}