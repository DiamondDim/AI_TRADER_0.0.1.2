from .mt5 import MT5
from .data import DataFetcher
from .trader import Trader
from .logger import setup_logger
from .config import Settings
from .realtime_monitor import RealTimeMonitor  # НОВЫЙ ИМПОРТ
from .strategies import (
    TradingStrategy, 
    SimpleMAStrategy, 
    RSIStrategy, 
    MACDStrategy,
    BollingerBandsStrategy,
    AdvancedMultiStrategy,
    get_available_strategies,
    create_strategy,
    STRATEGIES_REGISTRY
)

__all__ = [
    'MT5', 
    'DataFetcher', 
    'Trader', 
    'setup_logger', 
    'Settings',
    'RealTimeMonitor',  # НОВЫЙ ЭКСПОРТ
    'TradingStrategy',
    'SimpleMAStrategy', 
    'RSIStrategy',
    'MACDStrategy',
    'BollingerBandsStrategy',
    'AdvancedMultiStrategy',
    'get_available_strategies',
    'create_strategy',
    'STRATEGIES_REGISTRY'
]