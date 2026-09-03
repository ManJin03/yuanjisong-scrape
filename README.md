# 猿急送兼职项目智能筛选爬虫系统

面向大学生的猿急送（yuanjisong.com）兼职项目抓取与智能筛选系统：
**异步并发抓取 -> 黑名单过滤 -> 技术方向分类 -> 学生友好清单 -> Excel 多 Sheet 导出**。

## 功能模块

| 模块 | 文件 | 说明 |
|---|---|---|
| 爬虫抓取 | `scrape_lightweight.py` | 基于 `curl_cffi` 异步并发，模拟 Chrome 131 TLS 指纹，WAF 预热、指数退避重试、断点续爬、周期性落盘 |
| 代理池 | `proxy_pool.py` | 抓取免费代理并测活，按成功率加权随机，连续失败 3 次拉黑、5 分钟自动恢复；池空自动降级直连 |
| 智能过滤 | `smart_filter.py` | 内置四类黑名单（高难度 / 违规敏感 / 硬件 IoT / 游戏开发 / 驻场），命中原因写回字段可审计 |
| 技术分类 | `classify.py` | 关键词优先级归类 10 个方向（爬虫 / AI 智能体 / 小程序移动端 / 前端 / 后端接口 / Web 全栈 / 测试质检 / 运维部署 / 数据分析 / 工具脚本 + 其他） |
| 学生筛选 | `filter_student_projects.py` | 预算 ≤ 500 元、非驻场（远程）、未命中黑名单，按预算升序 -> 投递人数升序排序 |
| Excel 导出 | `exporter.py` | openpyxl 多 Sheet、表头样式、自适应列宽、冻结首行、职位超链接 |
| 数据模型 | `models.py` | `Project` 数据类 + SSR HTML 解析器（解析自真实页面结构） |
| 一键流水线 | `main.py` | `scrape` / `classify` / `student` / `all` 子命令 |

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

## 相比原始描述的优化

1. **可审计过滤**：黑名单命中类别与关键词写回 Excel，而非静默丢弃；
2. **派生字段防呆**：远程/驻场标志由 `work_type` 实时派生，手工构造数据同样生效；
3. **断点续爬强化**：页码 + 项目 ID 双重状态，`next_page` 单调递增防回退；
4. **页数预算精确**：并发调度下 `--pages N` 恰好抓 N 页（绝对页码上限）；
5. **分类优先级**：具体方向（爬虫/AI）优先于宽泛方向（前端/后端），减少误归类；
6. **代理池降级**：无可用代理自动直连，绝不因代理源故障阻塞任务；
7. **Excel 可用性**：冻结首行、列宽自适应、职位列可直接点击跳转；
8. **零额外依赖**：HTML 解析用标准库正则实现，不引入 bs4/lxml。
