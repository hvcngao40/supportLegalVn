import json
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tools.gemini_client import GeminiClient
from tools.qwen_dashscope_client import QwenDashScopeClient
from tools.qwen_ollama_client import QwenOllamaClient
from tools.deepseek_client import DeepSeekClient
from tools.groq_client import GroqClient
from tools.openrouter_client import OpenRouterClient


def _default_model_for_provider(provider_name: str) -> str:
    provider_name = provider_name.lower()
    if provider_name == "gemini":
        return "gemini-2.0-flash"
    if provider_name == "dashscope":
        return "qwen-plus"
    if provider_name == "ollama":
        return "qwen-14b-chat"
    if provider_name == "deepseek":
        return "deepseek-chat"
    if provider_name == "groq":
        return "llama-3.1-8b-instant"
    if provider_name == "openrouter":
        return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    return "llama-3.1-8b-instant"

class QueryClassification(BaseModel):
    """Schema for legal query classification results."""
    domains: List[str] = Field(description="List of legal domains relevant to the query")
    confidence: float = Field(description="Confidence score for the classification (0.0 to 1.0)")
    is_explicit_filter: bool = Field(description="True if user explicitly requested a specific law or document")
    nam_ban_hanh: Optional[int] = Field(None, description="Year of enactment if mentioned")
    linh_vuc: Optional[str] = Field(None, description="Specific legal field for filtering")


class LegalQueryClassifier:
    """Classifies legal queries into specific Vietnamese legal domains."""

    DOMAINS = {
        "Civil & Family": "Dân sự, Hôn nhân, Gia đình, Thừa kế, Hợp đồng dân sự",
        "Criminal": "Hình sự, Tội phạm, Khung hình phạt, Tố tụng hình sự",
        "Business & Commercial": "Doanh nghiệp, Thương mại, Thành lập công ty, Phá sản, Sở hữu trí tuệ",
        "Labor & Insurance": "Lao động, Bảo hiểm xã hội, Bảo hiểm y tế, Hợp đồng lao động",
        "Administrative & Tax": "Hành chính, Thuế, Xử phạt giao thông, Thủ tục hành chính",
        "Land & Real Estate": "Đất đai, Bất động sản, Sổ đỏ, Tranh chấp đất đai"
    }

    def __init__(
        self,
        provider: str = "groq",
        fallback_provider: str = "gemini",
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = provider.lower()
        self.fallback_provider = fallback_provider.lower()
        self.model_name = model_name or _default_model_for_provider(self.provider)
        self.api_key = api_key
        self._clients: Dict[str, Any] = {}

    async def classify(self, query: str) -> QueryClassification:
        """Classifies a user query with provider failover and safe fallback."""
        system_prompt = f"""Bạn là một chuyên gia pháp luật Việt Nam am hiểu sâu sắc về hệ thống văn bản quy phạm pháp luật.
Nhiệm vụ của bạn là phân tích câu hỏi của người dùng và phân loại chính xác vào các lĩnh vực luật tương ứng.

Dưới đây là danh sách các lĩnh vực và từ khóa nhận diện:
{self._format_domains()}

Yêu cầu phân loại:
1. Trả về kết quả dưới định dạng JSON duy nhất.
2. Trường 'domains': Danh sách các lĩnh vực liên quan (ví dụ: ["Criminal", "Land & Real Estate"]). Nếu câu hỏi chung chung hoặc không thuộc các nhóm trên, hãy dùng ["General"].
3. Trường 'confidence': Độ tin cậy của phân loại (0.0 đến 1.0).
4. Trường 'is_explicit_filter': Trả về True nếu người dùng nhắc đích danh một văn bản luật cụ thể (ví dụ: 'Luật Đất đai 2024', 'Nghị định 123', 'Điều 15 Bộ luật Hình sự').
5. Trường 'nam_ban_hanh': Trích xuất năm ban hành văn bản nếu có (ví dụ: 2024). Trả về null nếu không rõ.
6. Trường 'linh_vuc': Trích xuất lĩnh vực cụ thể để lọc (ví dụ: 'Hình sự', 'Đất đai'). Trả về null nếu không rõ.

Chú ý: DeepSeek, hãy phân tích kỹ ngữ cảnh pháp lý để đưa ra domains chính xác nhất. Không kèm theo giải thích hay markdown.

"""

        full_prompt = f"{system_prompt}\n\nCâu hỏi: {query}"

        # Try primary provider first, then fallback provider.
        for provider_name in [self.provider, self.fallback_provider]:
            if not provider_name:
                continue
            try:
                response = await self._call_provider(provider_name, full_prompt)
                content = getattr(response, "text", "").strip()
                data = self._parse_json_response(content)
                return QueryClassification(**data)
            except Exception as e:
                print(f"Classifier provider '{provider_name}' failed: {e}")

        return QueryClassification(domains=["General"], confidence=0.0, is_explicit_filter=False)

    async def _call_provider(self, provider_name: str, prompt: str) -> Any:
        client = self._get_client(provider_name)
        return await client.generate_content_async(prompt)

    def _get_client(self, provider_name: str) -> Any:
        provider_name = provider_name.lower()
        if provider_name in self._clients:
            return self._clients[provider_name]

        if provider_name == "gemini":
            model_name = self.model_name if self.model_name.startswith("gemini") else "gemini-2.0-flash"
            client = GeminiClient(model_name=model_name, api_key=self.api_key)
        elif provider_name == "dashscope":
            client = QwenDashScopeClient(model_name=self.model_name, api_key=self.api_key)
        elif provider_name == "ollama":
            client = QwenOllamaClient(model_name=self.model_name)
        elif provider_name == "deepseek":
            client = DeepSeekClient(model_name=self.model_name, api_key=self.api_key)
        elif provider_name == "groq":
            client = GroqClient(model_name=self.model_name, api_key=self.api_key)
        elif provider_name == "openrouter":
            client = OpenRouterClient(model_name=self.model_name)
        else:
            raise ValueError(f"Unsupported classifier provider: {provider_name}")

        self._clients[provider_name] = client
        return client

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        try:
            # Clean markdown if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)
        except Exception as e:
            raise ValueError(f"Invalid classifier JSON response: {e}") from e

    def _format_domains(self) -> str:
        return "\n".join([f"- {k}: {v}" for k, v in self.DOMAINS.items()])
