from strategies.alpha_edge_strategy import AlphaEdgeStrategy
from strategies.orderbook_scalper import OrderbookScalperStrategy
from strategies.candlestick_strategy import CandlestickPriceActionStrategy
from strategies.quant_strategy import QuantStatisticalStrategy
from strategies.institutional_trend import InstitutionalTrendStrategy

STRATEGY_REGISTRY = {
    "candlestick_action": CandlestickPriceActionStrategy,
    "quant_statistical": QuantStatisticalStrategy,
    "institutional_trend": InstitutionalTrendStrategy,
    "alpha_edge": AlphaEdgeStrategy,
    "orderbook_scalper": OrderbookScalperStrategy,
}

DEFAULT_STRATEGY = "institutional_trend"
