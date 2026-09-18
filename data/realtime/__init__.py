"""
Real-Time Indian Market Data Infrastructure for APEX-QUANT.

Provides normalized, validated, thread-safe, and fail-closed real-time
market data pipelines for Indian equities.
"""

from data.realtime.models import (
    NormalizedSymbol,
    ConnectionState,
    MarketSessionState,
    RealtimeQuote,
    FeedHealthMetrics,
    AggregatedBar,
)
from data.realtime.exceptions import (
    MarketDataError,
    MarketDataConnectionError,
    MarketDataValidationError,
    MarketDataStaleError,
    MarketDataProviderError,
    MarketDataSubscriptionError,
)
from data.realtime.normalizer import (
    SymbolNormalizer,
    QuoteNormalizer,
)
from data.realtime.validator import (
    RealtimeDataValidator,
    ValidationResult,
)
from data.realtime.cache import (
    LatestQuoteCache,
    get_global_quote_cache,
)
from data.realtime.health import (
    FeedHealthMonitor,
    get_global_health_monitor,
)
from data.realtime.reconnect import (
    ConnectionManager,
)
from data.realtime.provider import (
    RealTimeMarketDataProvider,
)
from data.realtime.mock_provider import (
    MockRealTimeProvider,
)
from data.realtime.safe_adapters import (
    KiteRealTimeFeedAdapter,
)
from data.realtime.bar_aggregator import (
    RealtimeBarAggregator,
)
from data.realtime.handoff import (
    HistoricalRealtimeHandoff,
)
from data.realtime.config import (
    RealtimeConfig,
    REALTIME_PROVIDER,
    REALTIME_MAX_STALENESS_SECONDS,
    REALTIME_RECONNECT_BASE_DELAY,
    REALTIME_RECONNECT_MAX_DELAY,
    REALTIME_RECONNECT_MAX_ATTEMPTS,
    REALTIME_BAR_INTERVAL_SECONDS,
    REALTIME_CLOCK_SKEW_TOLERANCE_SECONDS,
    DEFAULT_REALTIME_SYMBOLS,
)

__all__ = [
    # Models
    "NormalizedSymbol",
    "ConnectionState",
    "MarketSessionState",
    "RealtimeQuote",
    "FeedHealthMetrics",
    "AggregatedBar",
    # Exceptions
    "MarketDataError",
    "MarketDataConnectionError",
    "MarketDataValidationError",
    "MarketDataStaleError",
    "MarketDataProviderError",
    "MarketDataSubscriptionError",
    # Normalization & Validation
    "SymbolNormalizer",
    "QuoteNormalizer",
    "RealtimeDataValidator",
    "ValidationResult",
    # Cache & Health
    "LatestQuoteCache",
    "get_global_quote_cache",
    "FeedHealthMonitor",
    "get_global_health_monitor",
    # Connection & Provider
    "ConnectionManager",
    "RealTimeMarketDataProvider",
    "MockRealTimeProvider",
    "KiteRealTimeFeedAdapter",
    # Aggregation & Handoff
    "RealtimeBarAggregator",
    "HistoricalRealtimeHandoff",
    # Config
    "RealtimeConfig",
    "REALTIME_PROVIDER",
    "REALTIME_MAX_STALENESS_SECONDS",
    "REALTIME_RECONNECT_BASE_DELAY",
    "REALTIME_RECONNECT_MAX_DELAY",
    "REALTIME_RECONNECT_MAX_ATTEMPTS",
    "REALTIME_BAR_INTERVAL_SECONDS",
    "REALTIME_CLOCK_SKEW_TOLERANCE_SECONDS",
    "DEFAULT_REALTIME_SYMBOLS",
]
