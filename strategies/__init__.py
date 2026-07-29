from strategies.alpha_edge_strategy import AlphaEdgeStrategy
from strategies.orderbook_scalper import OrderbookScalperStrategy

STRATEGY_REGISTRY = {
    "alpha_edge": AlphaEdgeStrategy,
    "orderbook_scalper": OrderbookScalperStrategy,
}

DEFAULT_STRATEGY = "alpha_edge"
