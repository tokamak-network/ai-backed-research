"""Central model configuration loader.

Reads config/models.json and provides:
- Role-based model/provider lookup
- LLM instance factory with fallback chain
- Pricing data for cost estimation
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .llm.base import BaseLLM

logger = logging.getLogger(__name__)

# Resolve config path relative to project root (two levels up from this file)
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "models.json"

# Cached config data
_config_data: Optional[dict] = None


@dataclass
class ModelSpec:
    """A single model+provider pair."""
    model: str
    provider: str


@dataclass
class RoleConfig:
    """Complete configuration for a role."""
    role: str
    primary: ModelSpec
    fallback: List[ModelSpec]
    temperature: float
    max_tokens: int


def _load_config() -> dict:
    """Load and cache models.json."""
    global _config_data
    if _config_data is None:
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(f"Model config not found: {_CONFIG_PATH}")
        with open(_CONFIG_PATH) as f:
            _config_data = json.load(f)
    return _config_data


def reload_config():
    """Force reload config (useful for testing or hot-reload)."""
    global _config_data
    _config_data = None
    _load_config()


def get_role_config(role: str) -> RoleConfig:
    """Get model configuration for a role.

    Args:
        role: Role name (e.g. "writer", "moderator", "reviewer")

    Returns:
        RoleConfig with primary model, fallback chain, temperature, max_tokens

    Raises:
        KeyError: If role is not defined in config
    """
    config = _load_config()
    roles = config["roles"]
    if role not in roles:
        raise KeyError(f"Unknown role '{role}'. Available: {list(roles.keys())}")

    role_data = roles[role]

    # Handle tiered configuration
    if "tier" in role_data:
        tier_name = role_data["tier"]
        tiers = config.get("tiers", {})
        if tier_name not in tiers:
            raise KeyError(f"Unknown tier '{tier_name}' referenced by role '{role}'")

        tier_data = tiers[tier_name]
        primary_data = tier_data["primary"]
        fallback_data = tier_data.get("fallback", [])
    else:
        # Legacy: direct model specification
        primary_data = role_data["primary"]
        fallback_data = role_data.get("fallback", [])

    primary = ModelSpec(**primary_data)
    fallback = [ModelSpec(**f) for f in fallback_data]

    return RoleConfig(
        role=role,
        primary=primary,
        fallback=fallback,
        temperature=role_data.get("temperature", 0.7),
        max_tokens=role_data.get("max_tokens", 4096),
    )


def get_reviewer_rotation() -> List[ModelSpec]:
    """Get reviewer model rotation list from config.

    Returns a list of ModelSpec to cycle through when assigning reviewers.
    Falls back to the default reviewer tier if rotation is not configured.
    """
    config = _load_config()
    roles = config.get("roles", {})
    rotation = roles.get("reviewer_rotation", [])
    if rotation:
        return [ModelSpec(model=r["model"], provider=r["provider"]) for r in rotation]
    # Fallback: use default reviewer model for all
    rc = get_role_config("reviewer")
    return [rc.primary]


def _get_api_key(provider: str) -> str:
    """Get API key for a provider from environment.

    Priority: provider-specific key > LLM_API_KEY (shared/router key).
    """
    config = _load_config()
    provider_cfg = config.get("provider_config", {}).get(provider, {})

    # Try provider-specific env key
    env_key = provider_cfg.get("env_key", "")
    api_key = os.environ.get(env_key, "") if env_key else ""

    # Try alternate env key (e.g. ANTHROPIC_AUTH_TOKEN)
    if not api_key:
        alt_key = provider_cfg.get("env_key_alt", "")
        if alt_key:
            api_key = os.environ.get(alt_key, "")

    # Fallback to shared LLM_API_KEY (e.g. LiteLLM/OpenRouter router key)
    if not api_key:
        llm_cfg = config.get("provider_config", {}).get("llm", {})
        llm_key = llm_cfg.get("env_key", "")
        if llm_key:
            api_key = os.environ.get(llm_key, "")

    if not api_key:
        raise ValueError(
            f"No API key for provider '{provider}'. "
            f"Set {env_key} or LLM_API_KEY environment variable."
        )
    return api_key


def _get_base_url(provider: str) -> Optional[str]:
    """Get base URL for a provider from environment.

    Priority: provider-specific base_url > LLM_BASE_URL (shared/router URL).

    Note: Anthropic provider does NOT fallback to LLM_BASE_URL, as it should
    use the direct Anthropic API unless ANTHROPIC_BASE_URL is explicitly set.
    """
    config = _load_config()
    provider_cfg = config.get("provider_config", {}).get(provider, {})
    env_base_url = provider_cfg.get("env_base_url", "")
    base_url = os.environ.get(env_base_url, "") if env_base_url else ""

    # Anthropic & Google: only use direct API, no fallback to LLM_BASE_URL
    if provider in ("anthropic", "google"):
        return base_url or None

    # Other providers: fallback to shared LLM_BASE_URL (e.g. LiteLLM/OpenRouter endpoint)
    if not base_url:
        llm_cfg = config.get("provider_config", {}).get("llm", {})
        llm_base = llm_cfg.get("env_base_url", "")
        if llm_base:
            base_url = os.environ.get(llm_base, "")

    return base_url or None


def _create_llm(provider: str, model: str) -> BaseLLM:
    """Create an LLM instance for a specific provider and model.

    Args:
        provider: "anthropic" or "openai"
        model: Model identifier

    Returns:
        BaseLLM instance (ClaudeLLM or OpenAILLM)
    """
    api_key = _get_api_key(provider)
    base_url = _get_base_url(provider)

    if provider == "anthropic":
        from .llm.claude import ClaudeLLM
        return ClaudeLLM(api_key=api_key, model=model, base_url=base_url)
    elif provider == "openai":
        from .llm.openai import OpenAILLM
        return OpenAILLM(api_key=api_key, model=model, base_url=base_url)
    elif provider == "google":
        # If a custom base_url is present, use OpenAILLM (e.g. for LiteLLM routing)
        if base_url:
            from .llm.openai import OpenAILLM
            return OpenAILLM(api_key=api_key, model=model, base_url=base_url)
        else:
            from .llm.gemini import GeminiLLM
            return GeminiLLM(api_key=api_key, model=model)
    elif provider == "deepseek":
        from .llm.openai import OpenAILLM
        # Use DeepSeek API URL if no custom base_url is provided
        ds_base_url = base_url or "https://api.deepseek.com"
        return OpenAILLM(api_key=api_key, model=model, base_url=ds_base_url)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def create_llm_for_role(role: str) -> BaseLLM:
    """Create an LLM instance for a role, using the primary model.

    The fallback chain is NOT applied here — it is handled at the call site
    (e.g. WriterAgent._call_llm_once) where retry logic is appropriate.
    This function simply instantiates the primary model for the role.

    Args:
        role: Role name from config/models.json

    Returns:
        BaseLLM instance configured for the role's primary model
    """
    rc = get_role_config(role)
    try:
        return _create_llm(rc.primary.provider, rc.primary.model)
    except ValueError:
        # If primary fails to instantiate (e.g. missing API key), try fallbacks
        for fb in rc.fallback:
            try:
                logger.warning(
                    f"Primary model {rc.primary.model} unavailable for role '{role}', "
                    f"trying fallback {fb.model}"
                )
                return _create_llm(fb.provider, fb.model)
            except ValueError:
                continue
        raise ValueError(
            f"No available model for role '{role}'. "
            f"Tried: {rc.primary.model}, {[f.model for f in rc.fallback]}"
        )


def create_fallback_llm_for_role(role: str) -> Optional[BaseLLM]:
    """Create an LLM instance from the first available fallback for a role.

    Used by agents that maintain a separate fallback LLM (e.g. WriterAgent).

    Args:
        role: Role name from config/models.json

    Returns:
        BaseLLM instance for first available fallback, or None if no fallbacks
    """
    rc = get_role_config(role)
    for fb in rc.fallback:
        try:
            return _create_llm(fb.provider, fb.model)
        except ValueError:
            continue
    return None


def get_pricing(model: str) -> Dict[str, float]:
    """Get pricing for a model (per 1M tokens).

    Args:
        model: Model identifier

    Returns:
        Dict with "input" and "output" pricing in USD per 1M tokens
    """
    config = _load_config()
    pricing = config.get("pricing", {})
    return pricing.get(model, {"input": 3.0, "output": 15.0})


def get_all_pricing() -> Dict[str, Dict[str, float]]:
    """Get all model pricing data.

    Returns:
        Dict mapping model names to their pricing
    """
    config = _load_config()
    return config.get("pricing", {})


def get_reviewer_models() -> List[Dict]:
    """Get reviewer model assignments from reviewer_rotation config.

    Returns list of {"provider": ..., "model": ..., "fallback": [...]} dicts.
    Each entry may include a fallback list for provider failure resilience.
    Falls back to the reviewer tier's primary+fallback if rotation is not configured.
    """
    config = _load_config()
    rotation = config.get("roles", {}).get("reviewer_rotation", [])
    if rotation:
        return [
            {
                "provider": r["provider"],
                "model": r["model"],
                "fallback": r.get("fallback", []),
            }
            for r in rotation
        ]
    # Fallback: use reviewer tier primary + fallback
    rc = get_role_config("reviewer")
    models = [{"provider": rc.primary.provider, "model": rc.primary.model, "fallback": []}]
    for fb in rc.fallback:
        models.append({"provider": fb.provider, "model": fb.model, "fallback": []})
    return models
