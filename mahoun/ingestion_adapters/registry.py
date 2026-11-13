"""Explicit registry for producer adapters accepted by the governed server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .banking_law_adapter import BankingLawAdapter
from .iranian_law_adapter import IranianLawAdapter

AdapterFactory = Callable[..., Any]

_ADAPTERS: dict[str, AdapterFactory] = {
    "BankingLawAdapter": BankingLawAdapter,
    "IranianLawAdapter": IranianLawAdapter,
}

_ADAPTER_OBJECT_TYPES: dict[str, frozenset[str]] = {
    "BankingLawAdapter": frozenset({"LawArticle"}),
    "IranianLawAdapter": frozenset(
        {
            "LawChapter",
            "LawArticle",
            "LawClause",
            "LegalCondition",
            "LegalException",
            "LegalSanction",
            "LegalObligation",
            "LegalProhibition",
            "LegalPermission",
            "LegalRight",
            "LegalConcept",
            "LawReference",
        }
    ),
}


def registered_adapter_names() -> frozenset[str]:
    return frozenset(_ADAPTERS)


def create_adapter(name: str, **kwargs: Any) -> Any:
    try:
        factory = _ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported ingestion adapter: {name}") from exc
    return factory(**kwargs)


def registered_adapter_object_types() -> dict[str, frozenset[str]]:
    """Return the declarative label capabilities of registered adapters."""
    return dict(_ADAPTER_OBJECT_TYPES)
