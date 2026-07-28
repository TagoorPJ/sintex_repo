from typing import Dict
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TokenUsage:
    """Holds token usage stats for a single LLM call."""

    def __init__(
        self,
        prompt: int = 0,
        completion: int = 0,
        total: int = 0,
        cached_prompt: int = 0,   
    ):
        self.prompt = prompt
        self.completion = completion
        self.total = total
        self.cached_prompt = cached_prompt  

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt,
            "completion_tokens": self.completion,
            "total_tokens": self.total,
            "cached_prompt_tokens": self.cached_prompt, 
        }

    def __repr__(self) -> str:
        return (
            f"TokenUsage(prompt={self.prompt}, "
            f"completion={self.completion}, "
            f"total={self.total}, "
            f"cached_prompt={self.cached_prompt})" 
        )


def log_token_usage(conversation_id: str, usage: TokenUsage) -> None:
    logger.info(
        "Token usage recorded",
        extra={
            "conversation_id": conversation_id,
            "prompt_tokens": usage.prompt,
            "completion_tokens": usage.completion,
            "total_tokens": usage.total,
            "cached_prompt_tokens": usage.cached_prompt,  
        },
    )