"""
Centralized configuration management for MAHOUN.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    host: str = Field(default="localhost", env="MAHOUN_DB_HOST")
    port: int = Field(default=5432, env="MAHOUN_DB_PORT")
    username: str = Field(default="postgres", env="MAHOUN_DB_USERNAME")
    password: str = Field(default="", env="MAHOUN_DB_PASSWORD")
    database: str = Field(default="mahoun", env="MAHOUN_DB_NAME")

    model_config = SettingsConfigDict(env_prefix="MAHOUN_DB_")


class VectorStoreSettings(BaseSettings):
    """Vector store configuration."""
    provider: Literal["chroma", "faiss", "qdrant"] = Field(
        default="chroma", env="MAHOUN_VECTOR_STORE_PROVIDER"
    )
    host: str = Field(default="localhost", env="MAHOUN_VECTOR_STORE_HOST")
    port: int = Field(default=8000, env="MAHOUN_VECTOR_STORE_PORT")
    collection_name: str = Field(
        default="mahoun_documents", env="MAHOUN_VECTOR_STORE_COLLECTION"
    )

    model_config = SettingsConfigDict(env_prefix="MAHOUN_VECTOR_STORE_")


class LLMSettings(BaseSettings):
    """LLM service configuration."""
    provider: Literal["ollama", "openai", "huggingface"] = Field(
        default="ollama", env="MAHOUN_LLM_PROVIDER"
    )
    model: str = Field(default="llama2", env="MAHOUN_LLM_MODEL")
    base_url: str = Field(
        default="http://localhost:11434", env="MAHOUN_LLM_BASE_URL"
    )
    api_key: Optional[str] = Field(default=None, env="MAHOUN_LLM_API_KEY")
    temperature: float = Field(default=0.1, env="MAHOUN_LLM_TEMPERATURE")
    max_tokens: int = Field(default=500, env="MAHOUN_LLM_MAX_TOKENS")

    model_config = SettingsConfigDict(env_prefix="MAHOUN_LLM_")


class OCRSettings(BaseSettings):
    """OCR configuration."""
    default_engine: Literal["paddle", "tesseract", "easyocr"] = Field(
        default="paddle", env="MAHOUN_OCR_DEFAULT_ENGINE"
    )
    languages: str = Field(default="fa", env="MAHOUN_OCR_LANGUAGES")
    use_post_processing: bool = Field(
        default=True, env="MAHOUN_OCR_USE_POST_PROCESSING"
    )

    model_config = SettingsConfigDict(env_prefix="MAHOUN_OCR_")


class ChunkingSettings(BaseSettings):
    """Chunking configuration."""
    strategy: Literal["semantic", "fixed", "paragraph", "hybrid"] = Field(
        default="semantic", env="MAHOUN_CHUNKER_STRATEGY"
    )
    chunk_size: int = Field(default=512, env="MAHOUN_CHUNKER_CHUNK_SIZE")
    overlap: int = Field(default=50, env="MAHOUN_CHUNKER_OVERLAP")
    min_chunk_size: int = Field(default=100, env="MAHOUN_CHUNKER_MIN_SIZE")
    preserve_sentences: bool = Field(
        default=True, env="MAHOUN_CHUNKER_PRESERVE_SENTENCES"
    )
    preserve_paragraphs: bool = Field(
        default=True, env="MAHOUN_CHUNKER_PRESERVE_PARAGRAPHS"
    )
    dynamic_size: bool = Field(
        default=True, env="MAHOUN_CHUNKER_DYNAMIC_SIZE"
    )

    model_config = SettingsConfigDict(env_prefix="MAHOUN_CHUNKER_")


class ProcessingSettings(BaseSettings):
    """General processing configuration."""
    max_workers: int = Field(default=4, env="MAHOUN_MAX_WORKERS")
    batch_size: int = Field(default=10, env="MAHOUN_BATCH_SIZE")
    timeout_seconds: int = Field(default=300, env="MAHOUN_TIMEOUT_SECONDS")
    enable_metrics: bool = Field(default=True, env="MAHOUN_ENABLE_METRICS")
    log_level: str = Field(default="INFO", env="MAHOUN_LOG_LEVEL")

    @validator("log_level")
    def check_log_level(cls, v):
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of {allowed}")
        return v.upper()

    model_config = SettingsConfigDict(env_prefix="MAHOUN_")


class Settings(BaseSettings):
    """Main application settings."""
    database: DatabaseSettings = DatabaseSettings()
    vector_store: VectorStoreSettings = VectorStoreSettings()
    llm: LLMSettings = LLMSettings()
    ocr: OCRSettings = OCRSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    processing: ProcessingSettings = ProcessingSettings()

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        default="development", env="MAHOUN_ENVIRONMENT"
    )
    debug: bool = Field(default=False, env="MAHOUN_DEBUG")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.
    """
    return Settings()


# Convenience functions for backward compatibility
def get_database_settings() -> DatabaseSettings:
    return get_settings().database


def get_vector_store_settings() -> VectorStoreSettings:
    return get_settings().vector_store


def get_llm_settings() -> LLMSettings:
    return get_settings().llm


def get_ocr_settings() -> OCRSettings:
    return get_settings().ocr


def get_chunking_settings() -> ChunkingSettings:
    return get_settings().chunking


def get_processing_settings() -> ProcessingSettings:
    return get_settings().processing