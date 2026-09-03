# -*- coding: utf-8 -*-
from models import Project
from smart_filter import apply_blacklist, filter_valid_budget, hit_blacklist


def mk(**kw):
    base = dict(id="1", title="测试项目", budget=300, hours=2, hours_unit="天",
                work_type="项目制 全国远程", description="简单脚本")
    base.update(kw)
    return Project(**base)


def test_hit_violation():
    p = mk(title="赌博网站开发")
    assert hit_blacklist(p)[0] == "违规敏感"


def test_hit_hard():
    p = mk(description="需要系统架构设计与高并发经验")
    assert hit_blacklist(p)[0] == "高难度"


def test_hit_iot():
    p = mk(title="STM32 数据采集")
    assert hit_blacklist(p)[0] == "硬件IoT"


def test_hit_game():
    p = mk(description="Unity 制作休闲游戏")
    assert hit_blacklist(p)[0] == "游戏开发"


def test_clean_pass():
    p = mk(title="Python 批量处理 Excel")
    assert hit_blacklist(p) is None


def test_apply_blacklist_partitions():
    items = [mk(id="1", title="正常"), mk(id="2", title="翻墙工具")]
    kept, dropped = apply_blacklist(items)
    assert [p.id for p in kept] == ["1"]
    assert [p.id for p in dropped] == ["2"]
    assert dropped[0].blacklist_hit == "违规敏感"
    assert dropped[0].blacklist_word == "翻墙"


def test_filter_valid_budget():
    items = [mk(id="1", budget=100), mk(id="2", budget=0)]
    assert [p.id for p in filter_valid_budget(items)] == ["1"]
