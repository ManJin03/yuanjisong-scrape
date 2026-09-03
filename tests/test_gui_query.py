# -*- coding: utf-8 -*-
"""查询引擎（搜索/筛选/排序/摘要）单元测试 —— GUI 的核心纯逻辑。"""
from yuanjisong.gui_query import (
    CATEGORY_ALL,
    QueryState,
    apply_query,
    available_categories,
    summarize,
)
from yuanjisong.models import Project


def mk(**kw):
    base = dict(id="1", title="Python 小工具", budget=300, hours=2, hours_unit="天",
                work_type="项目制 全国远程", description="批量处理 Excel 的脚本",
                employer_name="张三", delivery_count=3, page=1)
    base.update(kw)
    return Project(**base)


def test_keyword_and_match():
    ps = [mk(id="1", description="爬虫 采集"),
          mk(id="2", description="爬虫 Vue"),
          mk(id="3", description="后端 接口")]
    q = QueryState(keyword="爬虫 vue")
    assert [p.id for p in apply_query(ps, q)] == ["2"]


def test_keyword_searches_employer_and_category():
    ps = [mk(id="1", employer_name="李四", category="前端"),
          mk(id="2", employer_name="王五", category="")]
    assert [p.id for p in apply_query(ps, QueryState(keyword="王五"))] == ["2"]
    assert [p.id for p in apply_query(ps, QueryState(keyword="前端"))] == ["1"]


def test_category_filter():
    ps = [mk(id="1", category="爬虫"), mk(id="2", category="前端")]
    q = QueryState(category="爬虫")
    assert [p.id for p in apply_query(ps, q)] == ["1"]
    assert len(apply_query(ps, QueryState(category=CATEGORY_ALL))) == 2


def test_budget_range():
    ps = [mk(id="1", budget=100), mk(id="2", budget=300), mk(id="3", budget=900)]
    q = QueryState(budget_min=200, budget_max=500)
    assert [p.id for p in apply_query(ps, q)] == ["2"]


def test_budget_max_zero_means_unlimited():
    ps = [mk(id="1", budget=100), mk(id="2", budget=99999)]
    assert len(apply_query(ps, QueryState())) == 2


def test_remote_only():
    ps = [mk(id="1", work_type="项目制 全国远程"), mk(id="2", work_type="项目制 北京驻场")]
    assert [p.id for p in apply_query(ps, QueryState(remote_only=True))] == ["1"]


def test_blacklist_exclusion_toggle():
    ps = [mk(id="1"), mk(id="2", title="赌博网站")]
    assert [p.id for p in apply_query(ps, QueryState())] == ["1"]
    assert len(apply_query(ps, QueryState(exclude_blacklist=False))) == 2


def test_student_mode_caps_budget_and_onsite():
    ps = [mk(id="1", budget=500),
          mk(id="2", budget=501),
          mk(id="3", budget=200, work_type="项目制 上海驻场"),
          mk(id="4", budget=200, title="翻墙工具")]
    assert [p.id for p in apply_query(ps, QueryState(student_mode=True))] == ["1"]


def test_student_mode_respects_lower_budget_max():
    ps = [mk(id="1", budget=100), mk(id="2", budget=400)]
    q = QueryState(student_mode=True, budget_max=200)
    assert [p.id for p in apply_query(ps, q)] == ["1"]


def test_sort_budget_ascending_invalid_last():
    ps = [mk(id="1", budget=500), mk(id="2", budget=100), mk(id="3", budget=0)]
    assert [p.id for p in apply_query(ps, QueryState())] == ["2", "1", "3"]


def test_sort_budget_descending():
    ps = [mk(id="1", budget=100), mk(id="2", budget=900)]
    assert [p.id for p in apply_query(ps, QueryState(sort_by="预算降序"))] == ["2", "1"]


def test_sort_delivery_then_budget():
    ps = [mk(id="1", delivery_count=5, budget=100),
          mk(id="2", delivery_count=2, budget=900),
          mk(id="3", delivery_count=2, budget=200)]
    assert [p.id for p in apply_query(ps, QueryState(sort_by="投递人数升序"))] == ["3", "2", "1"]


def test_sort_newest_first():
    ps = [mk(id="100"), mk(id="900"), mk(id="200")]
    assert [p.id for p in apply_query(ps, QueryState(sort_by="最新优先"))] == ["900", "200", "100"]


def test_apply_query_does_not_mutate_input():
    ps = [mk(id="2", budget=900), mk(id="1", budget=100)]
    apply_query(ps, QueryState())
    assert [p.id for p in ps] == ["2", "1"]


def test_summarize():
    ps = [mk(id="1", work_type="项目制 全国远程"),
          mk(id="2", work_type="项目制 北京驻场", budget=300)]
    s = summarize(ps)
    assert "共 2 条" in s and "远程 1" in s and "学生友好 1" in s


def test_available_categories_ordered():
    ps = [mk(id="1", category="前端"), mk(id="2", category="前端"),
          mk(id="3", category="爬虫")]
    assert available_categories(ps) == [CATEGORY_ALL, "前端", "爬虫"]
