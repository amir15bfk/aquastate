"""Index registry. Each index task registers its provider here."""
from __future__ import annotations

from core.services.indices.base import BaseIndexProvider
from core.services.indices.cmi import CMIProvider
from core.services.indices.eesi import EESIProvider
from core.services.indices.sai import SAIProvider
from core.services.indices.srri import SRRIProvider
from core.services.indices.ssi import SSIProvider

INDEX_REGISTRY: dict[str, BaseIndexProvider] = {}


def register(provider: BaseIndexProvider) -> BaseIndexProvider:
    INDEX_REGISTRY[provider.index_id] = provider
    return provider


register(SSIProvider())
register(CMIProvider())
register(SRRIProvider())
register(SAIProvider())
register(EESIProvider())

__all__ = ["INDEX_REGISTRY", "register"]
