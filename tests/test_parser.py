# -*- coding: utf-8 -*-
"""解析器测试：直接使用线上抓取的真实页面 fixture，保证结构对准。"""
from pathlib import Path

from models import Project, dedupe, parse_job_cards, parse_project_id

FIXTURE = Path(__file__).parent / "fixtures" / "job_page1.html"
TWO_CARDS = Path(__file__).parent / "fixtures" / "two_cards.html"


def parse_fixture():
    return parse_job_cards(FIXTURE.read_text(encoding="utf-8"), page=1)


def test_parse_count():
    assert len(parse_fixture()) == 20


def test_parse_fields():
    ps = parse_fixture()
    p = ps[0]
    assert p.id and p.id.isdigit()
    assert p.url.startswith("https://www.yuanjisong.com/job/")
    assert p.title
    assert p.budget > 0
    assert p.hours > 0 and p.hours_unit in ("天", "小时", "周", "月")
    assert "远程" in p.work_type or "驻场" in p.work_type or p.work_type
    assert p.delivery_count >= 0
    assert p.employer_name
    assert len(p.description) > 10


def test_remote_flag():
    ps = parse_fixture()
    assert any(p.is_remote for p in ps)


def test_unique_ids():
    ps = parse_fixture()
    ids = [p.id for p in ps]
    assert len(ids) == len(set(ids))


def test_two_cards_smoke():
    ps = parse_job_cards(TWO_CARDS.read_text(encoding="utf-8"))
    assert len(ps) == 2
    assert all(isinstance(p, Project) for p in ps)


def test_dedupe_keeps_latest():
    a = Project(id="1", title="old")
    b = Project(id="1", title="new")
    c = Project(id="2", title="x")
    assert [p.title for p in dedupe([a, b, c])] == ["new", "x"]


def test_parse_project_id():
    assert parse_project_id("https://www.yuanjisong.com/job/160059") == "160059"
    assert parse_project_id("160059") == "160059"
