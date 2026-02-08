"""Configuration management for AI research workflow."""

import os
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class LLMConfig:
    """Configuration for a specific LLM provider."""

    provider: str  # 'anthropic', 'openai', 'google'
    model: str
    api_key: str
    base_url: Optional[str] = None  # Custom API endpoint


@dataclass
class WorkflowConfig:
    """Configuration for research workflow."""

    max_review_rounds: int = 3
    score_threshold: float = 7.5
    results_dir: Path = Path("results")


class Config:
    """Global configuration manager.

    Loads configuration from environment variables and .env file.
    Provides convenient access to API keys and settings.
    """

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        """Normalize model name to API-compatible format.

        Removes date suffixes and fixes common naming issues.
        Examples:
            claude-opus-4-5-20251101 -> claude-opus-4.5
            claude-sonnet-4-20250514 -> claude-sonnet-4.5
            claude-sonnet-4-5 -> claude-sonnet-4.5

        Args:
            model: Model name (possibly with date suffix)

        Returns:
            Normalized model name
        """
        # Remove date suffixes (e.g., -20251101, -20250514)
        import re
        model = re.sub(r'-\d{8}$', '', model)

        # Fix hyphen vs dot issues
        model = model.replace('opus-4-5', 'opus-4.5')
        model = model.replace('sonnet-4-5', 'sonnet-4.5')

        # Handle malformed names like sonnet-4-20 or sonnet-4
        if 'sonnet-4' in model and 'sonnet-4.5' not in model:
            model = model.replace('sonnet-4', 'sonnet-4.5')
        if 'opus-4' in model and 'opus-4.5' not in model:
            model = model.replace('opus-4', 'opus-4.5')

        return model

    def __init__(self, env_file: Optional[Path] = None):
        """Initialize configuration.

        Args:
            env_file: Optional path to .env file (defaults to .env in current directory)
        """
        # Load environment variables from .env file
        if env_file and env_file.exists():
            load_dotenv(env_file)
        else:
            load_dotenv()  # Load from default .env location

        # Shared LLM key (LiteLLM/OpenRouter router key)
        self.llm_api_key = os.getenv("LLM_API_KEY")
        self.llm_base_url = os.getenv("LLM_BASE_URL")

        # Provider-specific keys (take priority over LLM_API_KEY)
        self.anthropic_api_key = (
            os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_AUTH_TOKEN")
            or self.llm_api_key
        )
        self.anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL") or self.llm_base_url
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or self.llm_api_key
        self.openai_base_url = os.getenv("OPENAI_BASE_URL") or self.llm_base_url
        self.google_api_key = os.getenv("GOOGLE_API_KEY")

        # Default models
        self.default_writer_model = self._normalize_model_name(
            os.getenv("DEFAULT_WRITER_MODEL", "claude-opus-4.5")
        )
        self.default_reviewer_model = self._normalize_model_name(
            os.getenv("DEFAULT_REVIEWER_MODEL", "claude-sonnet-4")
        )

        # Workflow settings
        self.max_review_rounds = int(os.getenv("MAX_REVIEW_ROUNDS", "3"))
        self.score_threshold = float(os.getenv("SCORE_THRESHOLD", "7.5"))
        self.results_dir = Path(os.getenv("RESULTS_DIR", "results"))

    def get_llm_config(
        self,
        provider: str,
        model: Optional[str] = None
    ) -> LLMConfig:
        """Get LLM configuration for a specific provider.

        Args:
            provider: Provider name ('anthropic', 'openai', 'google')
            model: Optional model override (uses default if not specified)

        Returns:
            LLMConfig with provider, model, and API key

        Raises:
            ValueError: If API key is not configured for provider
        """
        # Get API key for provider
        api_key_map = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "google": self.google_api_key,
        }

        api_key = api_key_map.get(provider)
        if not api_key:
            raise ValueError(
                f"API key not configured for provider '{provider}'. "
                f"Set {provider.upper()}_API_KEY environment variable."
            )

        # Get default model if not specified
        if not model:
            model_defaults = {
                "anthropic": self.default_reviewer_model,
                "openai": "gpt-4-turbo-preview",
                "google": "gemini-2.0-flash-exp",
            }
            model = model_defaults.get(provider, "unknown")

        # Normalize model name (remove date suffixes, fix formatting)
        model = self._normalize_model_name(model)

        # Get base URL if applicable
        base_url = None
        if provider == "anthropic":
            base_url = self.anthropic_base_url
        elif provider == "openai":
            base_url = self.openai_base_url

        return LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

    def get_workflow_config(self) -> WorkflowConfig:
        """Get workflow configuration.

        Returns:
            WorkflowConfig with max rounds, threshold, and results directory
        """
        return WorkflowConfig(
            max_review_rounds=self.max_review_rounds,
            score_threshold=self.score_threshold,
            results_dir=self.results_dir,
        )

    def validate(self) -> Dict[str, bool]:
        """Validate that all required API keys are configured.

        Returns:
            Dictionary mapping provider names to configuration status
        """
        return {
            "anthropic": bool(self.anthropic_api_key),
            "openai": bool(self.openai_api_key),
            "google": bool(self.google_api_key),
        }


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance (singleton).

    Returns:
        Global Config instance
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config):
    """Set global configuration instance.

    Args:
        config: Config instance to use globally
    """
    global _config
    _config = config
