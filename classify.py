# -*- coding: utf-8 -*-
"""技术分类：按关键词优先级把项目归入 10 个技术方向。

优先级设计：越具体、越稀缺的方向越靠前（爬虫 > AI > 小程序 > 前端 > 后端...），
避免“用 Vue 写爬虫面板”被粗分到前端。
"""
from __future__ import annotations

from collections import Counter

from models import Project
import config


def classify_one(project: Project) -> str:
    text = project.text_for_match
    for name, words in config.CATEGORY_KEYWORDS:
        for w in words:
            if w in text:
                return name
    return config.CATEGORY_OTHER


def classify_all(projects: list[Project]) -> list[Project]:
    for p in projects:
        p.category = classify_one(p)
    return projects


def category_summary(projects: list[Project]) -> dict[str, int]:
    c = Counter(p.category or config.CATEGORY_OTHER for p in projects)
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))
