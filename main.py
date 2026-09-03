# -*- coding: utf-8 -*-
"""项目统一入口。

用法：
  python main.py gui                    # 启动交互式读取/筛选软件（推荐）
  python main.py scrape  --pages 20
  python main.py classify
  python main.py student
  python main.py all     --pages 100
"""
from yuanjisong.cli import main

if __name__ == "__main__":
    main()
