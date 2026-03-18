# -*- coding: utf-8 -*-
"""
===================================
命令處理器模組
===================================

包含所有機器人命令的實現。
"""

from bot.commands.base import BotCommand
from bot.commands.help import HelpCommand
from bot.commands.status import StatusCommand
from bot.commands.analyze import AnalyzeCommand
from bot.commands.market import MarketCommand
from bot.commands.batch import BatchCommand
from bot.commands.ask import AskCommand
from bot.commands.chat import ChatCommand

# 所有可用命令（用於自動註冊）
ALL_COMMANDS = [
    HelpCommand,
    StatusCommand,
    AnalyzeCommand,
    MarketCommand,
    BatchCommand,
    AskCommand,
    ChatCommand,
]

__all__ = [
    'BotCommand',
    'HelpCommand',
    'StatusCommand',
    'AnalyzeCommand',
    'MarketCommand',
    'BatchCommand',
    'AskCommand',
    'ChatCommand',
    'MarketCommand',
    'BatchCommand',
    'ALL_COMMANDS',
]
