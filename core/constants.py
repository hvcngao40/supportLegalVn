import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SAFE_EMBEDDING_MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
SQLITE_PATH = os.getenv("SQLITE_DB_PATH", "sqlite_data/legal_poc.db")

# LLM Pricing configuration (USD per 1M tokens)
LLM_PRICING: Dict[str, Dict[str, Dict[str, float]]] = {
    "gemini": {
        "gemini-2.0-flash": {"input_cost_per_1m": 0.075, "output_cost_per_1m": 0.30},
        "gemini-1.5-flash": {"input_cost_per_1m": 0.075, "output_cost_per_1m": 0.30},
        "gemini-1.5-pro": {"input_cost_per_1m": 1.25, "output_cost_per_1m": 5.00},
    },
    "groq": {
        "llama-3.1-8b-instant": {"input_cost_per_1m": 0.05, "output_cost_per_1m": 0.08},
        "llama-3.3-70b-versatile": {"input_cost_per_1m": 0.59, "output_cost_per_1m": 0.79},
        "llama3-8b-8192": {"input_cost_per_1m": 0.05, "output_cost_per_1m": 0.08},
        "llama3-70b-8192": {"input_cost_per_1m": 0.59, "output_cost_per_1m": 0.79},
    },
    "deepseek": {
        "deepseek-chat": {"input_cost_per_1m": 0.14, "output_cost_per_1m": 0.28},
    },
    "openrouter": {
        "default": {"input_cost_per_1m": 0.15, "output_cost_per_1m": 0.60},
    }
}


def calculate_token_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates the token cost based on provider, model, and token counts.

    Args:
        provider: The LLM provider (e.g., 'gemini', 'groq', 'deepseek', 'openrouter').
        model: The specific model name.
        input_tokens: Number of prompt/input tokens.
        output_tokens: Number of completion/output tokens.

    Returns:
        The total cost of the execution in USD.
    """
    provider = provider.lower()
    model = model.lower()

    pricing_provider = LLM_PRICING.get(provider, {})
    model_pricing = pricing_provider.get(model)
    if not model_pricing:
        for key in pricing_provider:
            if key in model:
                model_pricing = pricing_provider[key]
                break

    if not model_pricing:
        if provider == "openrouter":
            model_pricing = LLM_PRICING["openrouter"]["default"]
        else:
            model_pricing = {"input_cost_per_1m": 0.15, "output_cost_per_1m": 0.60}

    input_cost = (input_tokens / 1_000_000) * model_pricing["input_cost_per_1m"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output_cost_per_1m"]

    return input_cost + output_cost


# Fail-safe LangSmith imports
try:
    from langsmith import traceable
except ImportError:
    def traceable(*args: Any, **kwargs: Any) -> Any:
        """Fail-safe fallback decorator when langsmith is not installed.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            The decorated function or a decorator function wrapper.
        """
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def decorator(func: Any) -> Any:
            return func
        return decorator


def _set_run_metadata(**kwargs: Any) -> None:
    """Saves metadata to the current active LangSmith run tree in a fail-safe way.

    Args:
        **kwargs: Key-value metadata fields to attach.
    """
    try:
        from langsmith.run_helpers import get_current_run_tree
        run_tree = get_current_run_tree()
        if run_tree:
            for k, v in kwargs.items():
                if v is not None:
                    run_tree.metadata[k] = v
    except Exception as e:
        logger.warning(f"Failed to set LangSmith run metadata: {e}")