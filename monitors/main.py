# -*- coding:utf-8 -*-

import sys
import os

from aioquant import quant


def initialize():
    from watchers.price import PriceWatcher
    PriceWatcher()


if __name__ == "__main__":
    config_file = sys.argv[1]
    quant.start(config_file, initialize)
