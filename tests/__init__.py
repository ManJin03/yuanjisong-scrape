# -*- coding: utf-8 -*-
"""tests 包初始化：让测试能 import 项目根目录模块。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
