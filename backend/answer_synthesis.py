"""최종 답변의 호환 상태를 구성합니다. 별도 LLM 합성은 실행하지 않습니다."""


def insufficient_answer(status: str = "insufficient_evidence") -> dict[str, object]:
    """Return a fixed answer that makes no unsupported assertions."""
    return {
        "status": status,
        "overview": None,
        "sections": [],
        "conclusion": None,
        "model": None,
        "reasoning": None,
    }
