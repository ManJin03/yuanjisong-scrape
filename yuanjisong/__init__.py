# -*- coding: utf-8 -*-
"""猿急送兼职项目智能筛选爬虫系统核心包。

模块一览：
- config                全局配置（URL/并发/路径/黑名单/分类词库）
- models               Project 数据模型与 SSR HTML 解析器
- scrape_lightweight   异步并发爬虫（断点续爬）
- proxy_pool           代理池（加权调度/拉黑/恢复）
- smart_filter         黑名单智能过滤
- classify             技术方向分类（10 类）
- filter_student_projects 学生友好项目筛选
- exporter             Excel 多 Sheet 导出
- gui_query            查询引擎（搜索/筛选/排序纯函数）
- webapp               交互式 Web 读取软件（搜索/筛选/重新爬取/导出）
- cli                  命令行入口
"""
__version__ = "1.0.0"
