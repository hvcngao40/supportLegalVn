from pydantic import BaseModel, Field
from typing import Optional

class SearchLegalContextArgs(BaseModel):
    """
    Schema đầu vào cho Tool tìm kiếm trích đoạn luật.
    """
    query: str = Field(
        ...,
        description="Tình huống pháp lý thực tế hoặc câu hỏi bằng tiếng Việt. "
                    "Ví dụ: 'Mức phạt lỗi không đội mũ bảo hiểm' hoặc 'Hành vi bạo lực học đường bị xử lý thế nào?'"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Số lượng trích đoạn luật liên quan nhất cần trả về. Mặc định là 5."
    )

class GetFullDocumentArgs(BaseModel):
    """
    Schema đầu vào cho Tool lấy toàn văn văn bản luật.
    """
    document_id: str = Field(
        ...,
        description="Mã định danh (ID) của văn bản pháp luật, nghị định hoặc thông tư. "
                    "Ví dụ: 'nd-100-2019-nd-cp'. Mã này thường được lấy từ kết quả của tool search_legal_context."
    )