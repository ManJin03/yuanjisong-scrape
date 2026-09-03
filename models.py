# -*- coding: utf-8 -*-
"""数据模型与列表页解析器：从猿急送 SSR HTML 中提取兼职项目结构化字段。"""
from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, asdict
from typing import Any

# ---- 预编译正则（对准真实页面 .job_card 结构） ----
# 终止条件：下一张卡片 / 分页 <ul> / 文本结尾（保证最后一张卡片也能捕获）
RE_CARD = re.compile(
    r'<div class="job_card">(.*?)(?=<div class="job_card">|<ul class="pagination|\Z)', re.S
)
RE_JOB_URL = re.compile(r'href="(https?://[^"]+/job/(\d+))" class="job_card_title_link"')
RE_TITLE = re.compile(r'<h4 class="job_card_title">(.*?)</h4>', re.S)
RE_POSTNUM = re.compile(r'class="i_post_num">(\d+)<')
RE_TAG_TYPE = re.compile(r'<span class="job_tag_type">(.*?)</span>', re.S)
RE_HOURS = re.compile(r'工时：\s*([\d.]+)\s*(天|小时|周|月)')
RE_DESC = re.compile(r'<span class="job_card_desc_label">描述：</span>(.*?)\s*</div>', re.S)
RE_PRICE = re.compile(r'<div class="job_card_price">\s*¥?\s*([\d,]+(?:\.\d+)?)\s*(?:<em>元</em>)?', re.S)
RE_EMPLOYER = re.compile(r'href="(https?://[^"]+/employer/(\d+))"')
RE_EMPLOYER_NAME = re.compile(r'class="job_card_publisher_name">(.*?)</a>', re.S)
RE_TAGS = re.compile(r'<[^>]+>')

ONSITE_KEYWORDS = ("驻场", "坐班", "现场办公")


def _clean(text: str) -> str:
    """去标签、还原实体、压缩空白。"""
    text = RE_TAGS.sub("", text or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Project:
    """一条兼职项目记录。is_remote / is_onsite 为派生属性，随 work_type 实时计算。"""
    id: str
    title: str = ""
    url: str = ""
    budget: int = 0                 # 预算（元），无法解析为 0
    budget_raw: str = ""            # 原始预算文本
    hours: float = 0.0              # 工时数值
    hours_unit: str = ""            # 天/小时/周/月
    work_type: str = ""             # 如“项目制 全国远程”
    status: str = "招募中"           # 页面未显式给出时默认
    description: str = ""
    delivery_count: int = 0         # 已投递人数
    employer_id: str = ""
    employer_name: str = ""
    employer_url: str = ""
    page: int = 0                   # 抓取来源页码
    category: str = ""              # 技术分类（classify 填充）
    blacklist_hit: str = ""         # 黑名单类别（filter 填充）
    blacklist_word: str = ""        # 命中关键词（filter 填充）

    @property
    def is_remote(self) -> bool:
        return "远程" in self.work_type

    @property
    def is_onsite(self) -> bool:
        wt = self.work_type.lower()
        return any(k in wt for k in ONSITE_KEYWORDS)

    @property
    def text_for_match(self) -> str:
        return f"{self.title} {self.work_type} {self.description}".lower()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_remote"], d["is_onsite"] = self.is_remote, self.is_onsite
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        valid = set(cls.__dataclass_fields__)  # 前向兼容：忽略旧版本多余字段
        return cls(**{k: v for k, v in d.items() if k in valid})


def parse_project_id(url_or_id: str) -> str:
    m = re.search(r"/job/(\d+)", url_or_id)
    return m.group(1) if m else str(url_or_id)


def parse_job_cards(page_html: str, page: int = 0) -> list[Project]:
    """解析一页 HTML，返回项目列表；单卡片字段缺失时降级为空值而不中断。"""
    projects: list[Project] = []
    for card in RE_CARD.findall(page_html):
        p = Project(id="", page=page)
        m = RE_JOB_URL.search(card)
        if m:
            p.url, p.id = m.group(1), m.group(2)
        m = RE_TITLE.search(card)
        p.title = _clean(m.group(1)) if m else ""
        m = RE_POSTNUM.search(card)
        p.delivery_count = int(m.group(1)) if m else 0
        m = RE_TAG_TYPE.search(card)
        p.work_type = _clean(m.group(1)) if m else ""
        m = RE_HOURS.search(card)
        if m:
            p.hours, p.hours_unit = float(m.group(1)), m.group(2)
        m = RE_DESC.search(card)
        p.description = _clean(m.group(1)) if m else ""
        m = RE_PRICE.search(card)
        if m:
            p.budget_raw = m.group(1)
            p.budget = int(float(m.group(1).replace(",", "")))
        m = RE_EMPLOYER.search(card)
        if m:
            p.employer_url, p.employer_id = m.group(1), m.group(2)
        m = RE_EMPLOYER_NAME.search(card)
        p.employer_name = _clean(m.group(1)) if m else ""
        if p.id:
            projects.append(p)
    return projects


def dedupe(projects: list[Project]) -> list[Project]:
    """按项目 ID 去重，保留后出现的（更新）记录，保持原有顺序。"""
    by_id: dict[str, Project] = {}
    for p in projects:
        by_id[p.id] = p
    return [by_id[k] for k in dict.fromkeys(p.id for p in projects)]


def save_json(projects: list[Project], path) -> None:
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([p.to_dict() for p in projects], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def load_json(path) -> list[Project]:
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return []
    return [Project.from_dict(d) for d in json.loads(p.read_text(encoding="utf-8"))]
