# -*- coding: utf-8 -*-
"""智能过滤：黑名单关键词命中检测，排除不适合大学生接取的项目。

优化点：不止“过滤掉”，而是把命中类别与命中词写回字段，
       Excel 里可审计每一条被排除的原因，课程答辩时可解释。
"""
from __future__ import annotations

from yuanjisong.models import Project
from yuanjisong import config


def hit_blacklist(project: Project) -> tuple[str, str] | None:
    """返回 (类别, 命中词)；未命中返回 None。标题权重最高，其次类型，最后描述。"""
    text = project.text_for_match
    for category, words in config.BLACKLIST.items():
        for word in words:
            if word in text:
                return category, word
    return None


def apply_blacklist(projects: list[Project]) -> tuple[list[Project], list[Project]]:
    """返回 (通过列表, 排除列表)；排除项已填充 blacklist_hit/blacklist_word。"""
    kept, dropped = [], []
    for p in projects:
        hit = hit_blacklist(p)
        if hit:
            p.blacklist_hit, p.blacklist_word = hit
            dropped.append(p)
        else:
            p.blacklist_hit, p.blacklist_word = "", ""
            kept.append(p)
    return kept, dropped


def filter_valid_budget(projects: list[Project]) -> list[Project]:
    """剔除预算无法解析（0）的记录，保证数值筛选可信。"""
    return [p for p in projects if p.budget > 0]
