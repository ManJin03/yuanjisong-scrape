# -*- coding: utf-8 -*-
"""学生友好项目筛选：预算 ≤500 元、非驻场（远程可做）、未被黑名单排除。

规则（在原始需求基础上的增强）：
1. 预算有效且 ≤ STUDENT_MAX_BUDGET；
2. 非驻场：优先看 work_type 是否含“驻场/坐班”，描述命中也排除；
3. 先过黑名单（违规/高难度/IoT/游戏天然不适合学生）；
4. 竞争度参考：投递人数越少越好，按 预算升序 -> 投递人数升序 排序。
"""
from __future__ import annotations

from models import Project
import config
from smart_filter import apply_blacklist, filter_valid_budget

ONSITE_WORDS = ("驻场", "坐班", "现场办公")


def is_student_friendly(project: Project) -> bool:
    if project.budget <= 0 or project.budget > config.STUDENT_MAX_BUDGET:
        return False
    if project.is_onsite:
        return False
    desc = project.description.lower()
    return not any(w in desc for w in ONSITE_WORDS)


def filter_student_projects(projects: list[Project]) -> list[Project]:
    kept, _dropped = apply_blacklist(projects)
    kept = filter_valid_budget(kept)
    result = [p for p in kept if is_student_friendly(p)]
    result.sort(key=lambda p: (p.budget, p.delivery_count, -float(p.hours or 0)))
    return result
