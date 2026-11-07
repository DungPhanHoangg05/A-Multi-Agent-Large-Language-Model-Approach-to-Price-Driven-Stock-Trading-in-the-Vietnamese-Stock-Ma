"""Giới hạn cứng của prompt MT-BICL trước lời gọi provider."""

def check_prompt_length(prompt: str) -> None:
    """Kiểm prompt đã render toàn bộ, không cắt distill/cap hoặc đếm thiếu separator."""
    if type(prompt) is not str or len(prompt) >= 6500:
        raise ValueError("FAIL_BUDGET: prompt Decision phải dưới 6500 ký tự")
