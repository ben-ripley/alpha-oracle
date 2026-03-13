"""Factory for creating the Anthropic client based on configured provider.

Supports two providers:
- "anthropic": Direct Anthropic API using ANTHROPIC_API_KEY
- "bedrock": AWS Bedrock using AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
  (or any credential source boto3 recognises: env vars, ~/.aws/credentials,
  instance profile, etc.)

Usage::

    from src.agents.client import get_anthropic_client
    client = get_anthropic_client()
    response = client.messages.create(...)
"""
from __future__ import annotations

import functools
from typing import Union


def get_anthropic_client() -> "Union[anthropic.Anthropic, anthropic.AnthropicBedrock]":
    """Return an Anthropic client configured for the active provider.

    The client is cached after first construction — call
    ``get_anthropic_client.cache_clear()`` in tests to reset it.
    """
    return _build_client()


@functools.lru_cache(maxsize=1)
def _build_client():
    import anthropic

    from src.core.config import get_settings
    settings = get_settings()
    agent_cfg = settings.agent

    if agent_cfg.provider == "bedrock":
        kwargs: dict = {"aws_region": agent_cfg.aws_region}
        if settings.aws_access_key_id:
            kwargs["aws_access_key"] = settings.aws_access_key_id
        if settings.aws_secret_access_key:
            kwargs["aws_secret_key"] = settings.aws_secret_access_key
        return anthropic.AnthropicBedrock(**kwargs)

    # Default: direct Anthropic API
    if not settings.anthropic_api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Set it in .env or switch to agent.provider=bedrock with AWS credentials."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)
