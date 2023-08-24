# -*- coding:utf-8 -*-

# 策略实现

from aioquant import const
from aioquant.utils import logger
from aioquant.configure import config
from aioquant.market import Market
from aioquant.const import BINANCE
from aioquant.market import Kline
from aioquant.market import Orderbook
from aioquant.utils import tools

import asyncio

from aioquant.utils.dingtalk import DingTalk

class PriceWatcher:   

    def __init__(self):
        """ 初始化
        """
        self.symbol = config.symbol

        self.count_down_time = 300
        # last sent price count down time, only allow resend if not in map
        self.last_send = {}
        self.klines_len = 60
        self.klines = []

        # 监控价格列表
        self.watch_list = [
            30000.0,
            29400.0,
            29380.0,
            29375.0,
            29350.0,
            29342.0,
            29340.0,
            29300.0
        ]
        
        # 订阅行情
        Market(symbol=self.symbol, market_type=const.MARKET_TYPE_KLINE_1S, callback=self.on_kline_update)

    async def on_kline_update(self, kline: Kline):
        """ 订单薄更新
        """
        logger.debug("user kline:", kline, caller=self)

        # update count down
        self.update_count_down()

        # update kline history
        if  len(self.klines) == self.klines_len:
            self.klines.pop(0)
        self.klines.append(kline)

        now_price = float(kline.open)
        last_avarage_price = 0.0
        for k in self.klines:
            last_avarage_price += float(k.open) / len(self.klines)

        break_throught = None
        price = None
        for watch_price in self.watch_list:
            if watch_price in self.last_send:
                continue
            if last_avarage_price < watch_price and now_price > watch_price :
                break_throught = "向上"
                price = watch_price
            if last_avarage_price > watch_price and now_price < watch_price :
                break_throught = "向下"
                price = watch_price

        if break_throught:
            self.add_count_down(price)
            time = tools.get_datetime_str()
            message = "\
                    {symbol}价格{break_throught}突破{price}\n               \
                    [{time}]\n                                              \
                    [价格变动]\n"                                           \
                    .format(
                time=time,symbol=kline.symbol,break_throught = break_throught, price=price) 
            logger.info("DingTalk:", message, caller=self)
            # await DingTalk.send_text_msg(message)

    def update_count_down(self):
        for price, time in self.last_send.items():
            if time == 1:
                self.last_send.pop(price)
            self.last_send[price] = time - 1
    def add_count_down(self, price):
        self.last_send[price] = self.count_down_time
