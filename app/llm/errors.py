class LLMError(Exception):
    """Base class; `user_message` is safe to show in the UI."""

    default_message = "The language model is not available right now."

    def __init__(self, user_message: str | None = None):
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


class LLMUnavailableError(LLMError):
    default_message = "The language model service is unavailable right now. Please try again in a minute."


class LLMAuthError(LLMError):
    default_message = "The Groq API key is missing or invalid. Set GROQ_API_KEY in .env and restart."


class LLMRateLimitError(LLMError):
    default_message = "Groq rate limit reached. Wait a moment and try again."
