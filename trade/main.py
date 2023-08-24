# -*- coding:utf-8 -*-

import sys
import os

from aioquant import quant
from aioquant.utils import logger
from aioquant.configure import config
from aioquant.binance import Binance

trader = None

def initialize():
    # 交易模块
    cc = {
        "strategy": "my_strategy",
        "platform": "binance",
        "symbol": config.symbol,
        "account": config.accounts[0]["account"],
        "access_key": config.accounts[0]["access_key"],
        "secret_key": config.accounts[0]["secret_key"],
        "testnet": config.testnet,
        "interval": "1s",
    }
    global trader 
    trader = Binance(**cc)
    
    from monitor.pricewatcher import PriceWatcher 
    PriceWatcher()
    
def close_connection():
    trader._ws.stop()
    

if __name__ == "__main__":
    config_file = sys.argv[1]
    quant.start(config_file, initialize, close_connection)
