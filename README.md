# 猿急送兼职项目智能筛选爬虫系统

面向大学生的猿急送（yuanjisong.com）兼职项目抓取与智能筛选系统：
**异步并发抓取 -> 黑名单过滤 -> 技术方向分类 -> 学生友好清单 -> Excel 多 Sheet 导出**。

## 功能模块

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 爬虫抓取 | `yuanjisong/scrape_lightweight.py` | 基于 `curl_cffi` 异步并发，模拟 Chrome 131 TLS 指纹，WAF 预热、指数退避重试、断点续爬、周期性落盘 |
| 代理池 | `yuanjisong/proxy_pool.py` | 抓取免费代理并测活，按成功率加权随机，连续失败 3 次拉黑、5 分钟自动恢复；池空自动降级直连 |
| 智能过滤 | `yuanjisong/smart_filter.py` | 内置四类黑名单（高难度 / 违规敏感 / 硬件 IoT / 游戏开发 / 驻场），命中原因写回字段可审计 |
| 技术分类 | `yuanjisong/classify.py` | 关键词优先级归类 10 个方向（爬虫 / AI 智能体 / 小程序移动端 / 前端 / 后端接口 / Web 全栈 / 测试质检 / 运维部署 / 数据分析 / 工具脚本 + 其他） |
| 学生筛选 | `yuanjisong/filter_student_projects.py` | 预算 ≤ 500 元、非驻场（远程）、未命中黑名单，按预算升序 -> 投递人数升序排序 |
| Excel 导出 | `yuanjisong/exporter.py` | openpyxl 多 Sheet、表头样式、自适应列宽、冻结首行、职位超链接 |
| 数据模型 | `yuanjisong/models.py` | `Project` 数据类 + SSR HTML 解析器（解析自真实页面结构） |
| 一键流水线 | `main.py` | `scrape` / `classify` / `student` / `all` 子命令 |

## 目录结构

```text
yuanjisong-scrape/
├── main.py                  # 统一入口（薄壳，转发到 yuanjisong.cli）
├── requirements.txt         # 依赖（curl_cffi / openpyxl / pytest）
├── .env.example             # 环境变量模板（代理订单等，可选）
├── yuanjisong/              # 核心包
│   ├── __init__.py
│   ├── cli.py               # 命令行入口：scrape/classify/student/gui/all
│   ├── webapp.py            # 交互式 Web 读取软件
│   └── gui_query.py         # 查询引擎（搜索/筛选/排序）
│   ├── config.py            # 全局配置与词库
│   ├── models.py            # Project 数据模型 + HTML 解析器
│   ├── scrape_lightweight.py# 异步并发爬虫（断点续爬）
│   ├── proxy_pool.py        # 代理池
│   ├── smart_filter.py      # 黑名单过滤
│   ├── classify.py          # 技术分类
│   ├── filter_student_projects.py # 学生筛选
│   └── exporter.py          # Excel 导出
├── tests/                   # Pytest 测试（fixtures 含真实页面样本）
│   └── fixtures/
├── output/                  # 运行产物（已 gitignore）
└── README.md / LICENSE
```

## 交互式读取软件（推荐入口）

**方式一（推荐，双击即用）**：运行项目根目录的 `run_gui.bat`
（自动使用 `.venv` 虚拟环境；首次运行会自动创建环境并安装依赖）

**方式二（命令行）**：

```bash
.venv\Scripts\python main.py gui   # 注意：用虚拟环境的 Python，启动后自动打开浏览器
```

> 依赖按需加载：浏览 / 搜索 / 筛选 / 分类无需任何第三方依赖即可使用；
> 仅「导出 Excel」需要 openpyxl、「重新爬取」需要 curl_cffi，缺失时界面会给出安装提示。
> 若直接用系统 `python main.py gui` 且未装依赖，不会崩溃——GUI 正常启动，对应功能按钮会提示安装方法。

零额外依赖（标准库 `http.server` 实现），功能：

- **读取**：一键载入 `output/projects.json`，表格展示标题/预算/工时/类型/投递/分类/黑名单/雇主/描述
- **重新爬取**：页数 / 并发 / 清空重爬三个参数，后台线程运行爬虫，日志面板实时输出，完成后自动刷新数据
- **搜索**：关键词多词 AND 匹配（标题/类型/描述/雇主/分类），输入即筛（250ms 防抖）
- **筛选**：技术分类下拉 / 预算区间 / 仅远程 / 排除黑名单 / 学生模式（≤500 元且非驻场，强制黑名单）
- **排序**：预算、投递人数、工时、最新，点击表头亦可切换
- **详情**：单击行查看完整描述与全部字段，双击打开职位链接，支持复制链接/标题
- **分类**：一键智能分类并持久化
- **导出**：导出全部 Excel（多 Sheet）或按当前筛选条件导出视图 Excel
- 学生模式行绿色高亮，黑名单行红标显示命中类别与关键词

技术说明：数据一次性载入浏览器，搜索/筛选/排序全部前端即时完成（2100 条毫秒级响应）；
爬取经 `/api/scrape` 由后台线程执行，进度经 `/api/scrape/status` 轮询回传。


## 安装

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

依赖仅 3 个库：`curl_cffi`、`openpyxl`、`pytest`。

## 使用

```bash
# 1. 抓取（全站约 800+ 页，每页 20 条；--pages 可限量试跑）
python main.py scrape --pages 20          # 抓前 20 页
python main.py scrape                     # 全量增量抓取（断点续爬）
python main.py scrape --fresh --pages 5   # 清空状态重抓 5 页
python main.py scrape --use-proxy         # 启用代理池轮转（可选）

# 2. 技术分类 -> output/projects.xlsx（全部 + 每个方向一个 Sheet）
python main.py classify

# 3. 学生友好清单 -> output/student_projects.xlsx
python main.py student

# 4. 一键全流程
python main.py all --pages 100
```

输出目录 `output/`：

- `projects.json` —— 全量结构化数据（UTF-8 JSON，含元字段）
- `state.json` —— 断点续爬状态（已完成页码 / 已见 ID / 下一起始页）
- `projects.xlsx` —— 全部项目 + 按技术方向分 Sheet
- `student_projects.xlsx` —— 学生友好清单（≤500 元、远程、按预算升序）

## 测试

```bash
python -m pytest tests -q
```

35 个单元测试覆盖：真实页面 fixture 解析（字段完整性 / 去重 / ID 唯一性）、
黑名单命中与分区、分类优先级（如「Vue 写爬虫面板」归爬虫而非前端）、
学生筛选排序规则、代理池加权调度 / 拉黑 / 恢复、Excel 导出结构。

## 架构与反爬说明（实测）

- 站点由阿里云 WAF 保护：同一会话先 GET 首页（挑战自动种 Cookie），
  再请求 `/job/allcity/page{N}` 即可 200；`curl_cffi` 的 `impersonate="chrome131"`
  负责 Chrome TLS 指纹，无需执行 JS。
- 列表页为服务端渲染 HTML，每页 20 条 `.job_card`，深层空页即数据终点。
- 并发 5 实测稳定（约 0.06s/页）；已内置超时、指数退避重试与失败熔断。
- 请合理控制频率与用途，仅抓取公开列表数据，遵守目标网站服务条款。
