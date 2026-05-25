from typing import Any, Dict, TypedDict


class RetrievalNode(TypedDict):
    id: str
    text: str
    metadata: Dict[str, Any]
    score: float


def make_retrieval_node(
    node_id: str,
    text: str,
    metadata: Dict[str, Any],
    score: float,
) -> RetrievalNode:
    return {
        "id": str(node_id),
        "text": text or "",
        "metadata": metadata,
        "score": float(score),
    }

