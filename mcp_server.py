import asyncio
from mcp.server.stdio import stdio_server

# Import mcp_server đã định nghĩa trong app.py của bạn
# (Giả định trong app.py bạn khai báo: mcp_server = Server("SupportLegalVn_MCP_Server"))
from app import mcp_server

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())