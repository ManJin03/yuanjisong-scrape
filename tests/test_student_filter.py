# -*- coding: utf-8 -*-
from yuanjisong.filter_student_projects import filter_student_projects, is_student_friendly
from yuanjisong.models import Project


def mk(**kw):
    base = dict(id="1", title="学生脚本", budget=300, hours=1, hours_unit="天",
                work_type="项目制 全国远程", description="Python 小工具")
    base.update(kw)
    return Project(**base)


def test_budget_limit():
    assert is_student_friendly(mk(budget=500))
    assert not is_student_friendly(mk(budget=501))
    assert not is_student_friendly(mk(budget=0))


def test_onsite_rejected():
    assert not is_student_friendly(mk(work_type="项目制 北京驻场"))
    assert not is_student_friendly(mk(description="需要现场办公驻场支持"))


def test_blacklisted_excluded():
    result = filter_student_projects([mk(id="1", title="赌博网站"), mk(id="2")])
    assert [p.id for p in result] == ["2"]


def test_sorted_by_budget_then_delivery():
    ps = [mk(id="1", budget=400, delivery_count=1),
          mk(id="2", budget=200, delivery_count=5),
          mk(id="3", budget=200, delivery_count=2)]
    result = filter_student_projects(ps)
    assert [p.id for p in result] == ["3", "2", "1"]
