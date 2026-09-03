# -*- coding: utf-8 -*-
from yuanjisong.classify import classify_all, classify_one, category_summary
from yuanjisong.models import Project
from yuanjisong import config


def mk(**kw):
    base = dict(id="1", title="t", budget=100, hours=1, hours_unit="天",
                work_type="项目制 全国远程", description="d")
    base.update(kw)
    return Project(**base)


def test_classify_spider():
    assert classify_one(mk(description="需要写爬虫采集数据，有反爬经验")) == "爬虫"


def test_classify_agent():
    assert classify_one(mk(title="LLM 智能体客服")) == "AI智能体"


def test_classify_miniprogram():
    assert classify_one(mk(description="微信小程序商城")) == "小程序移动端"


def test_classify_frontend():
    assert classify_one(mk(description="Vue3 组件开发")) == "前端"


def test_classify_backend():
    assert classify_one(mk(description="SpringBoot 接口开发")) == "后端接口"


def test_classify_script():
    assert classify_one(mk(description="写个自动化小工具批量处理文件")) == "工具脚本"


def test_classify_priority_spider_over_frontend():
    # “Vue 写爬虫管理面板”应优先归为爬虫而不是前端
    assert classify_one(mk(description="用 Vue 开发爬虫管理面板")) == "爬虫"


def test_classify_other():
    assert classify_one(mk(title="logo 设计", description="画图")) == config.CATEGORY_OTHER


def test_classify_all_and_summary():
    ps = [mk(id="1", description="爬虫"), mk(id="2", description="React 页面")]
    classify_all(ps)
    assert ps[0].category == "爬虫" and ps[1].category == "前端"
    s = category_summary(ps)
    assert s["爬虫"] == 1 and s["前端"] == 1
