# -*- coding: utf-8 -*-
"""交互式 Web 读取软件（stdlib 实现，GUI 本体零第三方依赖）。

架构：
- 后端：http.server + 后台爬取线程 + JSON API（127.0.0.1 本机监听）
- 前端：单页 HTML/CSS/JS，数据一次性载入浏览器，搜索/筛选/排序全部即时完成
- 原始三大筛选能力全部融合进 UI：黑名单过滤 / 技术分类 / 学生模式

依赖策略（按需延迟加载）：
- 浏览 / 搜索 / 筛选 / 分类 ......... 标准库即可，无第三方依赖
- 导出 Excel ....................... 需要 openpyxl（缺失时返回友好提示）
- 重新爬取 ......................... 需要 curl_cffi（缺失时日志提示安装方法）

API：
  GET  /                       前端页面
  GET  /api/data               项目列表(摘要) + 分类列表 + 统计
  GET  /api/project/<id>       项目完整详情
  POST /api/scrape             {pages, concurrency, fresh} 启动后台爬取
  GET  /api/scrape/status      {running, messages, count}
  POST /api/classify           智能分类并持久化
  POST /api/export/view        按当前筛选条件导出 Excel，返回路径
  POST /api/export/full        导出全部(多Sheet)+学生清单 Excel
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from yuanjisong import config
from yuanjisong.classify import category_summary, classify_all
from yuanjisong.filter_student_projects import filter_student_projects
from yuanjisong.gui_query import QueryState, apply_query, available_categories, summarize
from yuanjisong.models import Project, load_json, save_json

DONE_MARKER = "__SCRAPE_DONE__"

INSTALL_HINT = (
    "缺少依赖 {name}。请在项目目录执行：\n"
    "  .venv\\Scripts\\pip install -r requirements.txt\n"
    "或直接运行 run_gui.bat（自动使用虚拟环境）"
)


def missing_deps() -> list[str]:
    """检查可选依赖，返回缺失列表（不影响 GUI 启动浏览）。"""
    missing = []
    for mod in ("openpyxl", "curl_cffi"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


# ---------------------------------------------------------------- 数据层
class DataStore:
    """内存数据 + 线程锁，供 HTTP 线程与爬取线程共享。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.projects: list[Project] = []
        self.reload()

    def reload(self) -> list[Project]:
        with self.lock:
            self.projects = load_json(config.DATA_JSON)
            return self.projects

    def save(self) -> None:
        with self.lock:
            save_json(self.projects, config.DATA_JSON)

    def brief(self) -> list[dict]:
        with self.lock:
            return [{
                "id": p.id, "title": p.title, "budget": p.budget,
                "hours": f"{p.hours:g} {p.hours_unit}".strip(),
                "work_type": p.work_type,
                "is_remote": p.is_remote, "is_onsite": p.is_onsite,
                "delivery_count": p.delivery_count,
                "category": p.category or "其他",
                "blacklist_hit": p.blacklist_hit or "",
                "blacklist_word": p.blacklist_word or "",
                "employer": p.employer_name,
                "desc": p.description[:160] + ("…" if len(p.description) > 160 else ""),
            } for p in self.projects]

    def detail(self, pid: str) -> dict | None:
        with self.lock:
            p = next((x for x in self.projects if x.id == pid), None)
            if not p:
                return None
            return {
                "id": p.id, "title": p.title, "url": p.url, "budget": p.budget,
                "budget_raw": p.budget_raw, "hours": p.hours, "hours_unit": p.hours_unit,
                "work_type": p.work_type, "is_remote": p.is_remote,
                "is_onsite": p.is_onsite, "delivery_count": p.delivery_count,
                "category": p.category, "blacklist_hit": p.blacklist_hit,
                "blacklist_word": p.blacklist_word,
                "employer_name": p.employer_name, "employer_url": p.employer_url,
                "description": p.description,
            }


# ---------------------------------------------------------------- 爬取线程
class ScrapeManager:
    def __init__(self, store: DataStore):
        self.store = store
        self.messages: list[str] = []
        self.running = False
        self.lock = threading.Lock()

    def start(self, pages: int | None, concurrency: int, fresh: bool) -> tuple[bool, str]:
        with self.lock:
            if self.running:
                return False, "已有爬取任务进行中"
            try:
                import curl_cffi  # noqa: F401
            except ImportError:
                return False, INSTALL_HINT.format(name="curl_cffi")
            self.running = True
            self.messages = [f"[start] 页数={pages or '全量'} 并发={concurrency} 清空重爬={fresh}"]
        t = threading.Thread(target=self._worker, args=(pages, concurrency, fresh), daemon=True)
        t.start()
        return True, ""

    def _worker(self, pages: int | None, concurrency: int, fresh: bool) -> None:
        from yuanjisong.scrape_lightweight import Scraper

        if fresh:
            config.STATE_JSON.unlink(missing_ok=True)
            config.DATA_JSON.unlink(missing_ok=True)
            config.OUTPUT_DIR.mkdir(exist_ok=True)

        def progress(msg: str) -> None:
            with self.lock:
                self.messages.append(msg)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        scraper = Scraper(concurrency=concurrency, use_proxy=False, progress=progress)
        try:
            loop.run_until_complete(scraper.run(max_pages=pages))
        except Exception as e:  # noqa: BLE001
            with self.lock:
                self.messages.append(f"[error] {e}")
        finally:
            loop.run_until_complete(scraper.close())
            loop.close()
            self.store.reload()
            with self.lock:
                self.running = False
                self.messages.append(DONE_MARKER)

    def status(self) -> dict:
        with self.lock:
            done_seen = DONE_MARKER in self.messages
            shown = self.messages[:-1] if done_seen else self.messages
            return {
                "running": self.running,
                "messages": shown[-50:],
                "done": done_seen,
                "count": len(self.store.projects),
            }


# ---------------------------------------------------------------- 前端页面（同前版，略改：错误提示展示）
PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>猿急送兼职项目智能筛选系统</title>
<style>
:root{
  --bg:#f5f7fa; --panel:#ffffff; --side:#1e293b; --side2:#273548;
  --line:#e2e8f0; --txt:#1e293b; --dim:#64748b;
  --acc:#2563eb; --green:#059669; --red:#dc2626; --amber:#d97706;
  --green-bg:#ecfdf5; --red-bg:#fef2f2; --amber-bg:#fffbeb; --blue-bg:#eff6ff;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{display:flex;background:var(--bg);color:var(--txt);
     font:14px/1.65 "Microsoft YaHei UI","Segoe UI",system-ui,sans-serif;overflow:hidden}

/* ================= 左侧选项栏 ================= */
aside{width:292px;min-width:292px;height:100vh;overflow-y:auto;background:var(--side);
      color:#cbd5e1;display:flex;flex-direction:column}
.brand{padding:18px 20px 14px;border-bottom:1px solid #33415580}
.brand h1{font-size:16.5px;color:#fff;font-weight:600;letter-spacing:.5px}
.brand .sub{font-size:11.5px;color:#7d8ea5;margin-top:3px}
section{padding:14px 16px;border-bottom:1px solid #33415555}
section h4{font-size:11px;font-weight:600;color:#7d8ea5;letter-spacing:2px;
           margin-bottom:10px;padding-left:9px;position:relative}
section h4::before{content:"";position:absolute;left:0;top:2px;bottom:2px;width:3px;
                   border-radius:2px;background:var(--acc)}
.field{margin-bottom:10px}
.field:last-child{margin-bottom:0}
.field>span{display:block;font-size:12px;color:#8ba0b8;margin-bottom:4px}
.row2{display:flex;gap:8px;align-items:center}
.row2>span{flex:none}
aside button{width:100%;text-align:left;background:var(--side2);color:#dbe6f2;border:1px solid #3b4d64;
             border-radius:7px;padding:8px 12px;cursor:pointer;font-size:13px;
             margin-bottom:8px;transition:.15s;display:flex;align-items:center;gap:7px}
aside button:hover{border-color:var(--acc);color:#fff;background:#2c3d54}
aside button.primary{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
aside button.primary:hover{filter:brightness(1.12)}
aside button.green{background:#166534;border-color:#166534;color:#fff}
aside button.green:hover{filter:brightness(1.15)}
aside button:disabled{opacity:.45;cursor:not-allowed}
aside input[type=text],aside input[type=number],aside select{
  width:100%;background:#151f2e;color:#e5edf6;border:1px solid #3b4d64;border-radius:7px;
  padding:7px 10px;font-size:13px}
aside input:focus,aside select:focus{outline:none;border-color:var(--acc)}
aside .check{display:flex;align-items:center;gap:8px;padding:6px 2px;font-size:13px;
             cursor:pointer;user-select:none;border-radius:6px}
aside .check:hover{background:#ffffff10}
aside .check input{width:15px;height:15px;accent-color:var(--acc);cursor:pointer}
.side-stats{margin-top:auto;padding:14px 18px;font-size:12px;color:#7d8ea5;
            background:#18212e;border-top:1px solid #33415555}
.side-stats b{color:#e2e8f0;font-size:15px}

/* ================= 中间信息区 ================= */
main{flex:1;height:100vh;display:flex;flex-direction:column;min-width:0}
.topbar{background:var(--panel);border-bottom:1px solid var(--line);padding:12px 22px;
        display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.chip{background:var(--bg);border:1px solid var(--line);border-radius:16px;
      padding:4px 14px;font-size:12.5px;color:var(--dim)}
.chip b{color:var(--txt);font-size:14px;margin:0 2px}
.chip.hl{background:var(--green-bg);border-color:#a7f3d0;color:#047857}
.chip.hl b{color:#065f46}
.topbar .title{font-size:13px;color:var(--dim);margin-right:auto}

.table-wrap{flex:1;overflow:auto;background:var(--panel)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead th{position:sticky;top:0;z-index:2;background:#f1f5f9;color:#475569;font-weight:600;
         padding:10px 14px;text-align:left;cursor:pointer;user-select:none;white-space:nowrap;
         border-bottom:2px solid var(--line);font-size:12.5px}
thead th:hover{color:var(--acc)}
thead th.sorted{color:var(--acc)}
thead th.sorted::after{content:" ▲";font-size:10px}
thead th.sorted.desc::after{content:" ▼"}
tbody td{padding:10px 14px;border-bottom:1px solid #f1f5f9;vertical-align:top}
tbody tr:nth-child(even){background:#fafcfe}
tbody tr:hover{background:var(--blue-bg);cursor:pointer}
tbody tr.selected{background:#dbeafe;outline:1px solid #93c5fd}
tbody tr.student{background:var(--green-bg)}
tbody tr.student:nth-child(even){background:#e6fbf3}
tbody tr.student:hover{background:#d1fae5}
td.id,td.delivery{text-align:center;color:var(--dim);font-variant-numeric:tabular-nums}
td.money{text-align:right;font-weight:700;color:var(--green);white-space:nowrap;
         font-variant-numeric:tabular-nums}
td.title-cell{font-weight:600;max-width:300px}
.tag{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11.5px;
     white-space:nowrap;font-weight:500}
.tag.remote{background:#dbeafe;color:#1d4ed8}
.tag.onsite{background:var(--amber-bg);color:#b45309}
.tag.black{background:var(--red-bg);color:var(--red)}
.tag.cat{background:var(--green-bg);color:#047857}
.dim{color:var(--dim)}
td.desc-cell{color:#64748b;font-size:12.8px;max-width:520px}
.empty{padding:80px 20px;text-align:center;color:var(--dim);font-size:14px}

/* ================= 底部：详情/日志 ================= */
.bottom{height:250px;min-height:250px;border-top:1px solid var(--line);background:var(--panel);
        display:flex;flex-direction:column}
.tabs{display:flex;border-bottom:1px solid var(--line);background:#f8fafc}
.tabs button{background:none;border:none;border-right:1px solid var(--line);color:var(--dim);
             padding:9px 22px;font-size:13px;cursor:pointer}
.tabs button.active{background:var(--panel);color:var(--acc);font-weight:600;
                    border-bottom:2px solid var(--acc);margin-bottom:-1px}
.pane{flex:1;overflow:auto;display:none;padding:16px 22px}
.pane.active{display:block}
#detail h3{font-size:16px;margin-bottom:6px}
#detail .money{color:var(--green);font-size:18px;font-weight:700;margin-left:10px}
#detail .meta{display:flex;flex-wrap:wrap;gap:8px 22px;color:var(--dim);font-size:12.5px;
              margin:8px 0;padding:10px 14px;background:#f8fafc;border-radius:8px}
#detail .btns{display:flex;gap:8px;margin:6px 0 12px}
#detail .btns button{background:#fff;border:1px solid var(--line);border-radius:7px;
                     padding:6px 16px;font-size:13px;cursor:pointer;color:var(--txt)}
#detail .btns button.primary{background:var(--acc);border-color:var(--acc);color:#fff}
#detail .btns button:hover{border-color:var(--acc)}
#detail .desc{white-space:pre-wrap;font-size:13.5px;color:#334155;line-height:1.8}
#logBox{font-family:Consolas,"Courier New",monospace;font-size:12px;color:#475569;white-space:pre-wrap}
.hint{color:var(--dim);font-size:13px}
</style>
</head>
<body>

<!-- ============ 左侧：全部选项 ============ -->
<aside>
  <div class="brand">
    <h1>猿急送 · 智能筛选</h1>
    <div class="sub">兼职项目读取 / 爬取 / 搜索 / 筛选</div>
  </div>

  <section>
    <h4>数据操作</h4>
    <button onclick="reloadData()">↻ &nbsp;读取 / 刷新数据</button>
    <div class="field"><div class="row2">
      <span style="font-size:12px;color:#8ba0b8">页数</span>
      <input id="pages" type="number" min="1" placeholder="全量">
      <span style="font-size:12px;color:#8ba0b8">并发</span>
      <input id="conc" type="number" min="1" value="5" style="width:56px">
    </div></div>
    <label class="check"><input type="checkbox" id="fresh"> 清空重爬（丢弃历史重新开始）</label>
    <button id="scrapeBtn" class="primary" onclick="startScrape()">▶ &nbsp;重新爬取</button>
    <button onclick="runClassify()">⚡ &nbsp;智能分类（10 个技术方向）</button>
  </section>

  <section>
    <h4>筛选条件</h4>
    <div class="field"><span>关键词搜索（空格分隔多词）</span>
      <input id="kw" type="text" placeholder="例如：python 远程" oninput="onFilter()"></div>
    <div class="field"><span>技术分类</span>
      <select id="cat" onchange="onFilter()"><option>全部</option></select></div>
    <div class="field"><span>预算区间（元，留空不限）</span>
      <div class="row2">
        <input id="bmin" type="number" min="0" placeholder="≥ 下限">
        <span style="color:#8ba0b8">—</span>
        <input id="bmax" type="number" min="0" placeholder="≤ 上限">
      </div></div>
    <label class="check"><input type="checkbox" id="remote" onchange="onFilter()"> 仅显示远程项目</label>
    <label class="check"><input type="checkbox" id="noblack" checked onchange="onFilter()"> 排除黑名单项目</label>
    <label class="check"><input type="checkbox" id="student" onchange="onStudent()"> 学生模式（≤500 元 · 非驻场）</label>
  </section>

  <section>
    <h4>排序方式</h4>
    <div class="field">
      <select id="sort" onchange="onFilter()">
        <option>预算升序</option><option>预算降序</option>
        <option>投递人数升序</option><option>工时升序</option><option>最新优先</option>
      </select>
    </div>
    <button onclick="resetFilters()">✕ &nbsp;重置全部筛选</button>
  </section>

  <section>
    <h4>导出</h4>
    <button class="green" onclick="exportFull()">🗂 &nbsp;导出全部 Excel（分技术 Sheet）</button>
    <button onclick="exportView()">📄 &nbsp;导出当前视图 Excel</button>
  </section>

  <div class="side-stats" id="sideStats">—</div>
</aside>

<!-- ============ 中间：信息区 ============ -->
<main>
  <div class="topbar">
    <span class="title">猿急送兼职项目 · 数据浏览</span>
    <span class="chip">共 <b id="totalCount">0</b> 条</span>
    <span class="chip hl">显示 <b id="viewCount">0</b> 条</span>
    <span class="chip">远程 <b id="remoteCount">0</b></span>
    <span class="chip">学生友好 <b id="studentCount">0</b></span>
  </div>

  <div class="table-wrap">
    <table>
      <thead><tr>
        <th data-k="id" style="width:76px">ID</th>
        <th data-k="title" style="min-width:220px">标题</th>
        <th data-k="budget" style="width:92px">预算</th>
        <th data-k="hours" style="width:86px">工时</th>
        <th style="width:150px">合作类型</th>
        <th data-k="delivery_count" style="width:64px">投递</th>
        <th data-k="category" style="width:104px">技术分类</th>
        <th style="width:88px">状态</th>
        <th style="width:110px">雇主</th>
        <th style="min-width:360px">描述摘要</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display:none">
      暂无数据 —— 可在左侧点击「重新爬取」，或调整筛选条件
    </div>
  </div>

  <div class="bottom">
    <div class="tabs">
      <button id="tab-detail" class="active" onclick="showTab('detail')">项目详情</button>
      <button id="tab-log" onclick="showTab('log')">爬取日志</button>
    </div>
    <div id="detail" class="pane active">
      <p class="hint">点击表格中任意一行查看完整信息；双击直接打开职位链接。</p>
    </div>
    <div id="logPane" class="pane"><div id="logBox">等待操作…</div></div>
  </div>
</main>

<script>
let ALL = [], VIEW = [], selectedId = null, pollTimer = null;

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function showTab(name){
  $("tab-detail").classList.toggle("active", name==="detail");
  $("tab-log").classList.toggle("active", name==="log");
  $("detail").classList.toggle("active", name==="detail");
  $("logPane").classList.toggle("active", name==="log");
}

async function api(path, opts){
  const r = await fetch(path, opts);
  if(!r.ok){
    const e = await r.json().catch(()=>({error:r.statusText}));
    throw new Error(e.error || r.statusText);
  }
  return r.json();
}
function fail(e, tag){ showTab("log"); log("["+tag+"] "+e.message); alert(e.message); }

async function reloadData(){
  try{
    const d = await api("/api/data");
    ALL = d.projects;
    const sel = $("cat"), cur = sel.value;
    sel.innerHTML = d.categories.map(c=>`<option>${esc(c)}</option>`).join("");
    if(d.categories.includes(cur)) sel.value = cur;
    onFilter();
  }catch(e){ fail(e,"load"); }
}

function onStudent(){
  if($("student").checked) $("noblack").checked = true;
  onFilter();
}

function onFilter(){
  const kw = $("kw").value.trim().toLowerCase();
  const terms = kw ? kw.split(/\s+/) : [];
  const cat = $("cat").value, bmin = +$("bmin").value||0, bmax = +$("bmax").value||0;
  const remote = $("remote").checked, noblack = $("noblack").checked, student = $("student").checked;
  const sort = $("sort").value;

  VIEW = ALL.filter(p=>{
    if(student){
      if(p.blacklist_hit || p.budget<=0 || p.budget>500 || p.is_onsite) return false;
    } else if(noblack && p.blacklist_hit) return false;
    if(terms.length){
      const hay = (p.title+" "+p.work_type+" "+p.desc+" "+p.employer+" "+p.category).toLowerCase();
      if(!terms.every(t=>hay.includes(t))) return false;
    }
    if(cat!=="全部" && p.category!==cat) return false;
    if(bmin>0 && p.budget<bmin) return false;
    if(bmax>0 && (p.budget<=0 || p.budget>bmax)) return false;
    if(remote && !p.is_remote) return false;
    return true;
  });

  const invalid = p=>p.budget<=0;
  if(sort==="预算升序") VIEW.sort((a,b)=>(invalid(a)-invalid(b))||a.budget-b.budget||a.delivery_count-b.delivery_count);
  else if(sort==="预算降序") VIEW.sort((a,b)=>(invalid(a)-invalid(b))||b.budget-a.budget);
  else if(sort==="投递人数升序") VIEW.sort((a,b)=>a.delivery_count-b.delivery_count||a.budget-b.budget);
  else if(sort==="工时升序") VIEW.sort((a,b)=>(parseFloat(a.hours)-parseFloat(b.hours)));
  else if(sort==="最新优先") VIEW.sort((a,b)=>+b.id-+a.id);
  markSortedHeader(sort);

  render();
  const remoteN = VIEW.filter(p=>p.is_remote).length;
  const studentN = VIEW.filter(p=>!p.blacklist_hit&&p.budget>0&&p.budget<=500&&!p.is_onsite).length;
  $("totalCount").textContent = ALL.length;
  $("viewCount").textContent = VIEW.length;
  $("remoteCount").textContent = remoteN;
  $("studentCount").textContent = studentN;
  $("sideStats").innerHTML =
    `当前视图 <b>${VIEW.length}</b> 条 / 共 ${ALL.length} 条<br>` +
    `远程 ${remoteN} · 学生友好 ${studentN}`;
}

function markSortedHeader(sort){
  const map = {"预算升序":"budget","预算降序":"budget","投递人数升序":"delivery_count",
               "工时升序":"hours","最新优先":"id"};
  document.querySelectorAll("thead th").forEach(th=>{
    th.classList.remove("sorted","desc");
    if(th.dataset.k && map[sort]===th.dataset.k){
      th.classList.add("sorted");
      if(sort.includes("降序")) th.classList.add("desc");
    }
  });
}

function render(){
  const tb = $("tbody");
  const student = $("student").checked;
  const frag = [];
  for(const p of VIEW.slice(0,3000)){
    const cls = [student?"student":"", p.id===selectedId?"selected":""].join(" ");
    const status = p.blacklist_hit
      ? `<span class="tag black" title="命中：${esc(p.blacklist_word)}">${esc(p.blacklist_hit)}</span>`
      : (p.is_onsite ? `<span class="tag onsite">驻场</span>` : `<span class="tag remote">远程</span>`);
    frag.push(`<tr class="${cls}" data-id="${p.id}" onclick="showDetail('${p.id}')" ondblclick="openLink('${p.id}')">
      <td class="id">${p.id}</td>
      <td class="title-cell">${esc(p.title)}</td>
      <td class="money">¥${p.budget}</td>
      <td>${esc(p.hours)}</td>
      <td class="dim">${esc(p.work_type)}</td>
      <td class="delivery">${p.delivery_count}</td>
      <td>${p.category&&p.category!=="其他" ? `<span class="tag cat">${esc(p.category)}</span>` : `<span class="dim">其他</span>`}</td>
      <td>${status}</td>
      <td class="dim">${esc(p.employer)}</td>
      <td class="desc-cell">${esc(p.desc)}</td></tr>`);
  }
  tb.innerHTML = frag.join("");
  $("empty").style.display = VIEW.length ? "none":"block";
}

async function showDetail(id){
  selectedId = id;
  showTab("detail");
  document.querySelectorAll("tr.selected").forEach(e=>e.classList.remove("selected"));
  const row = document.querySelector(`tr[data-id="${id}"]`);
  if(row) row.classList.add("selected");
  const p = await api("/api/project/"+id);
  $("detail").innerHTML = `
    <h3>${esc(p.title)}<span class="money">¥${p.budget}</span></h3>
    <div class="meta">
      <span>工时：${esc(p.hours)} ${esc(p.hours_unit)}</span>
      <span>类型：${esc(p.work_type)}</span>
      <span>投递：${p.delivery_count} 人</span>
      <span>分类：<span class="tag cat">${esc(p.category||"未分类")}</span></span>
      <span>雇主：${esc(p.employer_name)}</span>
      ${p.blacklist_hit ? `<span style="color:var(--red)">黑名单：${esc(p.blacklist_hit)}（${esc(p.blacklist_word)}）</span>`:""}
    </div>
    <div class="btns">
      <button class="primary" onclick="window.open('${esc(p.url)}')">打开职位链接</button>
      <button onclick="copyText('${esc(p.url)}')">复制链接</button>
      <button onclick="copyText('${esc(p.title)}（¥${p.budget}） ${esc(p.url)}')">复制标题+预算</button>
    </div>
    <div class="desc">${esc(p.description)}</div>`;
}

function openLink(id){ window.open("/api/redirect/"+id); }
function copyText(t){ navigator.clipboard.writeText(t); }

document.querySelectorAll("thead th[data-k]").forEach(th=>{
  th.onclick = ()=>{
    const map = {budget:["预算升序","预算降序"],delivery_count:["投递人数升序","最新优先"],
                 hours:["工时升序","预算升序"],id:["最新优先","预算升序"],title:["预算升序","预算降序"],
                 category:["最新优先","预算升序"],employer:["最新优先","预算升序"]};
    const k = th.dataset.k;
    if(map[k]){ const cur=$("sort").value; $("sort").value = cur===map[k][0]?map[k][1]:map[k][0]; onFilter(); }
  };
});

function resetFilters(){
  ["kw","bmin","bmax"].forEach(i=>$(i).value="");
  $("cat").value="全部"; $("remote").checked=false;
  $("noblack").checked=true; $("student").checked=false; $("sort").value="预算升序";
  onFilter();
}

async function startScrape(){
  const pages = $("pages").value ? +$("pages").value : null;
  const conc = Math.max(1, +$("conc").value||5);
  const fresh = $("fresh").checked;
  $("scrapeBtn").disabled = true;
  showTab("log"); log("[start] 正在启动爬取…");
  try{
    const r = await api("/api/scrape",{method:"POST",headers:{"Content-Type":"application/json"},
                                      body:JSON.stringify({pages,concurrency:conc,fresh})});
    if(!r.started){ $("scrapeBtn").disabled=false; log("[scrape] "+r.error); alert(r.error); return; }
    if(!pollTimer) pollScrape();
  }catch(e){ $("scrapeBtn").disabled=false; fail(e,"scrape"); }
}

async function pollScrape(){
  try{
    const s = await api("/api/scrape/status");
    log(s.messages.join("\n"));
    if(s.running){ pollTimer = setTimeout(pollScrape,800); }
    else{
      pollTimer = null; $("scrapeBtn").disabled=false;
      if(s.done){ await reloadData(); }
    }
  }catch(e){ pollTimer=null; $("scrapeBtn").disabled=false; }
}

async function runClassify(){
  try{
    const r = await api("/api/classify",{method:"POST"});
    showTab("log"); log("[classify] "+JSON.stringify(r.summary));
    await reloadData();
  }catch(e){ fail(e,"classify"); }
}

async function exportFull(){
  try{
    const r = await api("/api/export/full",{method:"POST"});
    log("[export] "+r.paths.join("\n"));
    alert("已导出：\n"+r.paths.join("\n"));
  }catch(e){ fail(e,"export"); }
}

async function exportView(){
  try{
    const body = collectFilters();
    const r = await api("/api/export/view",{method:"POST",headers:{"Content-Type":"application/json"},
                                            body:JSON.stringify(body)});
    log("[export] "+r.path);
    alert("已导出 "+r.count+" 条：\n"+r.path);
  }catch(e){ fail(e,"export"); }
}

function collectFilters(){
  return {keyword:$("kw").value, category:$("cat").value,
          budget_min:+$("bmin").value||0, budget_max:+$("bmax").value||0,
          remote_only:$("remote").checked, exclude_blacklist:$("noblack").checked,
          student_mode:$("student").checked, sort_by:$("sort").value};
}

function log(msg){
  if(!msg) return;
  $("logBox").textContent = msg.split("\n").slice(-40).join("\n");
}

reloadData();
pollScrape();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- HTTP 服务
def make_handler(store: DataStore, scraper: ScrapeManager):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 安静模式
            pass

        def _json(self, obj, code: int = 200) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        # ---------- GET ----------
        def do_GET(self):
            if self.path == "/":
                html = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            elif self.path == "/api/data":
                projects = store.brief()
                summary = summarize(store.projects) if store.projects else "共 0 条"
                self._json({"projects": projects,
                            "categories": available_categories(store.projects),
                            "summary": summary})
            elif self.path.startswith("/api/project/"):
                pid = self.path.rsplit("/", 1)[-1]
                d = store.detail(pid)
                self._json(d if d else {"error": "not found"}, 200 if d else 404)
            elif self.path == "/api/scrape/status":
                self._json(scraper.status())
            elif self.path.startswith("/api/redirect/"):
                pid = self.path.rsplit("/", 1)[-1]
                d = store.detail(pid)
                if d and d["url"]:
                    self.send_response(302)
                    self.send_header("Location", d["url"])
                    self.end_headers()
                else:
                    self._json({"error": "not found"}, 404)
            else:
                self._json({"error": "not found"}, 404)

        # ---------- POST ----------
        def do_POST(self):
            try:
                if self.path == "/api/scrape":
                    body = self._body()
                    pages = body.get("pages")
                    concurrency = max(1, int(body.get("concurrency", config.CONCURRENCY)))
                    fresh = bool(body.get("fresh"))
                    ok, err = scraper.start(pages if pages and pages > 0 else None,
                                            concurrency, fresh)
                    self._json({"started": ok, "error": err})
                elif self.path == "/api/classify":
                    if not store.projects:
                        self._json({"summary": {}, "count": 0})
                        return
                    classify_all(store.projects)
                    store.save()
                    self._json({"summary": category_summary(store.projects),
                                "count": len(store.projects)})
                elif self.path in ("/api/export/full", "/api/export/view"):
                    try:
                        from yuanjisong.exporter import (
                            export_all_excel, export_excel, export_student_excel,
                        )
                    except ImportError:
                        self._json({"error": INSTALL_HINT.format(name="openpyxl")}, 500)
                        return
                    if self.path == "/api/export/full":
                        projects = classify_all(store.projects)
                        p1 = export_all_excel(projects)
                        p2 = export_student_excel(filter_student_projects(projects))
                        self._json({"paths": [str(p1), str(p2)]})
                    else:
                        body = self._body()
                        q = QueryState(
                            keyword=body.get("keyword", ""),
                            category=body.get("category", "全部"),
                            budget_min=int(body.get("budget_min", 0)),
                            budget_max=int(body.get("budget_max", 0)),
                            remote_only=bool(body.get("remote_only")),
                            exclude_blacklist=bool(body.get("exclude_blacklist", True)),
                            student_mode=bool(body.get("student_mode")),
                            sort_by=body.get("sort_by", "预算升序"),
                        )
                        view = apply_query(store.projects, q)
                        stamp = time.strftime("%Y%m%d_%H%M%S")
                        path = config.OUTPUT_DIR / f"当前视图_{stamp}.xlsx"
                        export_excel(view, path, sheet_name="当前视图")
                        self._json({"path": str(path), "count": len(view)})
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

    return Handler


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """启动 Web 软件：自动选择可用端口并打开浏览器。"""
    store = DataStore()
    scraper = ScrapeManager(store)
    for mod in missing_deps():
        print(f"[gui] 警告：{INSTALL_HINT.format(name=mod)}")
    server = None
    for candidate in range(port, port + 25):
        try:
            server = ThreadingHTTPServer((host, candidate), make_handler(store, scraper))
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError("8765-8789 端口均被占用")
    url = f"http://{host}:{port}/"
    print(f"[gui] 猿急送智能筛选软件已启动：{url}（Ctrl+C 退出）")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[gui] 已退出")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
