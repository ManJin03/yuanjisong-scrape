# 猿急送兼职项目智能筛选爬虫系统

面向大学生的猿急送（yuanjisong.com）兼职项目抓取与智能筛选系统：
**异步并发抓取 -> 黑名单过滤 -> 技术方向分类 -> 学生友好清单 -> Excel 多 Sheet 导出**。

提供**图形界面**（桌面端 / 网页端，功能完全相同）与**命令行流水线**两种使用方式，
推荐使用桌面端应用（免装 Python、双击即用）。

---

## 一、快速开始：两种使用方案

| | 方案一：桌面端应用（**推荐**） | 方案二：网页端（备选） |
| --- | --- | --- |
| 启动方式 | 双击 exe，原生窗口 | 命令行启动，自动打开浏览器 |
| 运行环境 | 无需安装 Python 和任何依赖 | 需要 Python 3.10+ 及项目依赖 |
| 适用场景 | 日常使用、分发给他人在 Windows 上使用 | 开发调试、macOS/Linux 环境临时使用 |
| 界面与功能 | 与网页端完全一致（同一套代码） | 与桌面端完全一致 |
| 数据 | exe 同级 `output\` 目录 | 项目根目录 `output/` |

### 方案一：桌面端应用（推荐）

**A. 拿到现成产物（最简）**：从仓库 Releases 页面下载 `yuanjisong-desktop-<版本>.zip`
（由 GitHub Actions 自动构建发布），或从已有的 `dist\猿急送筛选系统\` 目录（约 36MB）中
双击 `猿急送筛选系统.exe` 即可运行，无需安装任何东西。
分发给他人时，**将整个 `猿急送筛选系统` 目录压缩发送**即可。

**B. 从源码构建产物**（Windows，仅构建者需要）：

```bash
build_desktop.bat
```

脚本自动完成：检查/创建 `.venv` 虚拟环境 → 安装运行与构建依赖 → PyInstaller 打包 →
输出产物到 `dist\猿急送筛选系统\`。双击产物中的 exe 即用。

桌面端说明：

- 界面为 pywebview 原生窗口（Windows 使用系统自带的 Edge WebView2），窗口关闭即退出；
  若 WebView2 不可用，会自动退回浏览器模式，功能不受影响
- 数据目录：运行时自动在 exe 同级创建 `output\`；**升级 exe 时保留 `output\` 即可继承数据与断点续爬状态**
- 启动异常排查：查看 exe 同级的 `desktop_error.log`
- 本地服务仅监听 127.0.0.1:8765，端口被占用时自动顺延（最多到 8789）

### 方案二：网页端（备选）

```bash
run_gui.bat                              # 双击运行（自动建环境装依赖）
.venv\Scripts\python main.py gui         # 或命令行启动，自动打开浏览器
```

---

## 二、使用指南（两种方案通用）

图形界面采用「左侧选项栏 + 中间信息区」布局：
左栏集中数据操作与筛选控制，中栏为统计胶囊、项目表格与「项目详情 / 爬取日志」标签页；
学生模式行绿色高亮、黑名单行红标显示命中类别与关键词、远程蓝标，一眼可辨。

界面功能：

- **读取**：一键载入 `output/projects.json`，表格展示标题/预算/工时/类型/投递/分类/黑名单/雇主/描述
- **重新爬取**：页数 / 并发 / 清空重爬三个参数，后台线程运行爬虫，日志面板实时输出，完成后自动刷新数据
- **搜索**：关键词多词 AND 匹配（标题/类型/描述/雇主/分类），输入即筛（250ms 防抖）
- **筛选**：技术分类下拉 / 预算区间 / 仅远程 / 排除黑名单 / 学生模式（≤500 元且非驻场，强制黑名单）
- **排序**：预算、投递人数、工时、最新，点击表头亦可切换
- **详情**：单击行查看完整描述与全部字段，双击打开职位链接，支持复制链接/标题
- **分类**：一键智能分类并持久化
- **导出**：导出全部 Excel（多 Sheet）或按当前筛选条件导出视图 Excel

### 命令行流水线（可选）

不进界面也可以直接用命令行完成全流程：

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

### 数据文件（`output/` 目录）

| 文件 | 说明 |
| --- | --- |
| `projects.json` | 全量结构化数据（UTF-8 JSON，含元字段），界面的数据源 |
| `state.json` | 断点续爬状态（已完成页码 / 已见 ID / 下一起始页） |
| `projects.xlsx` | 全部项目 + 按技术方向分 Sheet |
| `student_projects.xlsx` | 学生友好清单（≤500 元、远程、按预算升序） |

桌面端运行时，以上文件位于 exe 同级 `output\`；源码运行时位于项目根目录 `output/`。

---

## 三、安装（源码运行）

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

依赖仅 4 个库：`curl_cffi`、`openpyxl`、`pywebview`（桌面端）、`pytest`。

> 依赖按需加载：浏览 / 搜索 / 筛选 / 分类无需任何第三方依赖即可使用；
> 仅「导出 Excel」需要 openpyxl、「重新爬取」需要 curl_cffi，缺失时界面会给出安装提示，
> 不会崩溃。

---

## 四、项目构建与目录结构

### 从源码构建桌面端

```bash
git clone <repo> && cd yuanjisong-scrape
build_desktop.bat        # 一键构建，产物：dist\猿急送筛选系统\
```

构建要点（详见 `yuanjisong.spec`）：

- onedir + windowed 模式：启动快、无控制台黑窗
- 显式收集 `cffi`（curl_cffi 的运行时动态依赖，静态分析探测不到）、`curl_cffi`（含 libcurl DLL）、`openpyxl`、`webview`（含 Windows 后端 pythonnet/clr_loader）
- 排除 pytest 等运行时无关模块
- 打包后数据路径自动锚定到 exe 同级目录（`sys.frozen` 检测）

### 自动构建与发布（GitHub Actions）

仓库已配置工作流 `.github/workflows/build-desktop.yml`（windows-latest 运行器，最小步骤：安装依赖 → 打包 → 压缩）：

| 触发方式 | 行为 |
| --- | --- |
| 推送 tag：`git tag v1.0.0 && git push origin v1.0.0` | 打包 → **自动发布 Release**（附 zip 与自动生成说明） |
| 推送 master / Actions 页面「Run workflow」 | 仅构建，产物在 Actions 的 Artifacts 中下载 |

发版步骤：

```bash
git tag v1.0.0
git push origin v1.0.0        # 推送后约 3-5 分钟，Release 页面出现 zip 附件
```

Release 中的 `yuanjisong-desktop-<tag>.zip` 解压即得完整应用目录，双击 exe 运行。
（CI 脚本内统一使用 ASCII 文件名，规避 Windows 运行器脚本编码问题；压缩包内的应用目录与 exe 仍为中文名）

### 目录结构

```text
yuanjisong-scrape/
├── main.py                  # 统一入口（薄壳，转发到 yuanjisong.cli）
├── desktop_app.py           # 桌面端 PyInstaller 打包入口（薄壳）
├── yuanjisong.spec          # PyInstaller 打包配置（onedir + windowed）
├── build_desktop.bat        # 桌面端一键构建脚本（Windows）
├── run_gui.bat              # 网页端启动脚本（自动建环境装依赖）
├── requirements.txt         # 依赖（curl_cffi / openpyxl / pywebview / pytest）
├── .env.example             # 环境变量模板（代理订单等，可选）
├── yuanjisong/              # 核心包（桌面端/网页端/命令行共用）
│   ├── cli.py               # 命令行入口：scrape/classify/student/gui/desktop/all
│   ├── desktop.py           # 桌面端壳（pywebview 窗口 + 后台 webapp 服务）
│   ├── webapp.py            # 交互式 Web 读取软件（内嵌单页前端）
│   ├── gui_query.py         # 查询引擎（搜索/筛选/排序）
│   ├── config.py            # 全局配置、路径与词库（黑名单/分类）
│   ├── models.py            # Project 数据模型 + SSR HTML 解析器
│   ├── scrape_lightweight.py# 异步并发爬虫（断点续爬）
│   ├── proxy_pool.py        # 代理池
│   ├── smart_filter.py      # 黑名单过滤
│   ├── classify.py          # 技术分类
│   ├── filter_student_projects.py # 学生筛选
│   └── exporter.py          # Excel 导出
├── .github/workflows/       # GitHub Actions：自动构建/测试/发布 Release
├── tests/                   # Pytest 测试（fixtures 含真实页面样本）
├── output/                  # 运行产物（已 gitignore）
└── README.md / LICENSE
```

---

## 五、项目实现

### 功能模块

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 爬虫抓取 | `yuanjisong/scrape_lightweight.py` | 基于 `curl_cffi` 异步并发，模拟 Chrome 131 TLS 指纹，WAF 预热、指数退避重试、断点续爬、周期性落盘 |
| 代理池 | `yuanjisong/proxy_pool.py` | 抓取免费代理并测活，按成功率加权随机，连续失败 3 次拉黑、5 分钟自动恢复；池空自动降级直连 |
| 智能过滤 | `yuanjisong/smart_filter.py` | 内置四类黑名单（高难度 / 违规敏感 / 硬件 IoT / 游戏开发 / 驻场），命中原因写回字段可审计 |
| 技术分类 | `yuanjisong/classify.py` | 关键词优先级归类 10 个方向（爬虫 / AI 智能体 / 小程序移动端 / 前端 / 后端接口 / Web 全栈 / 测试质检 / 运维部署 / 数据分析 / 工具脚本 + 其他） |
| 学生筛选 | `yuanjisong/filter_student_projects.py` | 预算 ≤ 500 元、非驻场（远程）、未命中黑名单，按预算升序 -> 投递人数升序排序 |
| Excel 导出 | `yuanjisong/exporter.py` | openpyxl 多 Sheet、表头样式、自适应列宽、冻结首行、职位超链接 |
| 数据模型 | `yuanjisong/models.py` | `Project` 数据类 + SSR HTML 解析器（解析自真实页面结构） |
| 图形界面 | `yuanjisong/webapp.py` | 标准库 `http.server` + 内嵌单页前端，零第三方界面依赖 |
| 桌面端 | `yuanjisong/desktop.py` | pywebview 原生窗口壳 + 后台运行 webapp 服务，窗口关闭即退出 |

### 架构设计

桌面端与网页端**共享同一套核心包与数据**，零逻辑分叉：

- 桌面端 = pywebview 原生窗口 + 后台线程运行 webapp 本地服务（127.0.0.1），网页端 = 同一服务 + 系统浏览器
- 数据一次性载入内存，搜索/筛选/排序全部前端即时完成（2100 条毫秒级响应）
- 爬取经 `/api/scrape` 由后台线程执行，进度经 `/api/scrape/status` 轮询回传
- 依赖按需延迟加载（见「安装」一节的说明）

### 架构与反爬说明（实测）

- 站点由阿里云 WAF 保护：同一会话先 GET 首页（挑战自动种 Cookie），
  再请求 `/job/allcity/page{N}` 即可 200；`curl_cffi` 的 `impersonate="chrome131"`
  负责 Chrome TLS 指纹，无需执行 JS。
- 列表页为服务端渲染 HTML，每页 20 条 `.job_card`，深层空页即数据终点。
- 并发 5 实测稳定（约 0.06s/页）；已内置超时、指数退避重试与失败熔断。
- 请合理控制频率与用途，仅抓取公开列表数据，遵守目标网站服务条款。

---

## 六、测试

```bash
python -m pytest tests -q
```

63 个单元测试覆盖：真实页面 fixture 解析（字段完整性 / 去重 / ID 唯一性）、
黑名单命中与分区、分类优先级（如「Vue 写爬虫面板」归爬虫而非前端）、
学生筛选排序规则、代理池加权调度 / 拉黑 / 恢复、Excel 导出结构、Web API 与界面查询。
