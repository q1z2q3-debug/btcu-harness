"""BTCU Harness configuration."""

from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global configuration for BTCU Harness."""

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "btcu_harness"

    # LLM
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Cognitive space
    num_dimensions: int = 9

    # Growth stage: school / internalize / graduate
    growth_stage: str = "school"

    model_config = {"env_prefix": "BTCU_", "env_file": ".env"}


settings = Settings()
