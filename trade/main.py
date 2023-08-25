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
        "account": config.account,
        "access_key": config.keys["binance"]["access_key"],
        "secret_key": config.keys["binance"]["secret_key"],
        "testnet": config.testnet,
        "interval": "1s",
    }
    if config.testnet:
        cc["access_key"] = config.keys["testnet"]["access_key"]
        cc["secret_key"] = config.keys["testnet"]["secret_key"]
        
    global trader 
    trader = Binance(**cc)
    
    from monitor.pricewatcher import PriceWatcher 
    PriceWatcher()
    
def close_connection():
    trader._ws.stop()
    

if __name__ == "__main__":
    if len(sys.argv) != 3:
        logger.error("miss params to start! need config_file_path and key_file_path")
        exit(1)
    config_file = sys.argv[1]
    key_file = sys.argv[2]
    quant.start(config_file, key_file, initialize, close_connection)
