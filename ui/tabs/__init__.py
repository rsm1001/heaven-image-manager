"""Tabs模块初始化"""
from .extract_tab import create_extract_tab
from .data_tab import create_data_tab
from .stats_tab import create_stats_tab
from .validator_tab import create_validator_tab

__all__ = [
    'create_extract_tab',
    'create_data_tab',
    'create_stats_tab',
    'create_validator_tab'
]
