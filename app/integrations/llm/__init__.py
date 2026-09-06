"""Optional LLM infrastructure adapters.

LLM adapters may parse user intent, but they do not own authorization,
approval, provider secrets, or any money-moving operation.
"""

from .deepseek import DeepSeekIntentParser, LLMIntentParseError

__all__ = ["DeepSeekIntentParser", "LLMIntentParseError"]
