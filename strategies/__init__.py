from strategies.crypto_futures_hunter import CryptoFuturesHunterStrategy
from strategies.institutional_trend import InstitutionalTrendStrategy
from strategies.alpha_edge_strategy import AlphaEdgeStrategy
from strategies.orderbook_scalper import OrderbookScalperStrategy

STRATEGY_REGISTRY = {
    "crypto_futures_hunter": CryptoFuturesHunterStrategy,
    "institutional_trend": InstitutionalTrendStrategy,
    "alpha_edge": AlphaEdgeStrategy,
    "orderbook_scalper": OrderbookScalperStrategy,
}

DEFAULT_STRATEGY = "crypto_futures_hunter"
