"""
Provider abstraction layer for Gold Price data sources
Supports modular, switchable market data providers
"""

from .base_provider import BaseProvider, ProviderResponse, ProviderError
from .metalprice_provider import MetalpriceProvider
from .finnhub_provider import FinnhubProvider
from .gold_api_provider import GoldApiProvider

__all__ = [
    'BaseProvider',
    'ProviderResponse',
    'ProviderError',
    'MetalpriceProvider',
    'FinnhubProvider',
    'GoldApiProvider',
]
