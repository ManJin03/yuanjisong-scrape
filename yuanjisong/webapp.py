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
:root{--bg:#0f141a;--panel:#171e26;--panel2:#1d2630;--line:#2a3644;
--txt:#dce4ec;--dim:#8496a6;--acc:#4da3ff;--green:#3ecf8e;--red:#ff6b6b;--amber:#ffb454}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font:14px/1.6 "Microsoft YaHei UI",system-ui,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 18px;background:var(--panel);border-bottom:1px solid var(--line)}
header h1{font-size:17px;font-weight:600}
header .sub{color:var(--dim);font-size:12px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 18px;background:var(--panel);border-bottom:1px solid var(--line)}
button{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:6px 14px;cursor:pointer;font-size:13px;transition:.15s}
button:hover{border-color:var(--acc);color:var(--acc)}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc)}
button.primary:hover{filter:brightness(1.1)}
button:disabled{opacity:.45;cursor:not-allowed}
input,select{background:var(--bg);color:var(--txt);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font-size:13px}
input:focus,select:focus{outline:none;border-color:var(--acc)}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 18px;background:var(--panel);border-bottom:1px solid var(--line)}
.filters label{display:flex;align-items:center;gap:5px;color:var(--dim);font-size:13px;white-space:nowrap}
.stats{display:flex;gap:18px;padding:8px 18px;color:var(--dim);font-size:12.5px;border-bottom:1px solid var(--line);background:#131a22}
.stats b{color:var(--txt)}
main{display:flex;flex-direction:column;height:calc(100vh - 210px)}
.table-wrap{flex:1;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{position:sticky;top:0;background:var(--panel2);color:var(--dim);font-weight:500;padding:9px 10px;text-align:left;cursor:pointer;user-select:none;border-bottom:1px solid var(--line);white-space:nowrap}
thead th:hover{color:var(--acc)}
tbody td{padding:8px 10px;border-bottom:1px solid #1c2530;vertical-align:top}
tbody tr:hover{background:#1a232e;cursor:pointer}
tbody tr.selected{background:#1c2b3a}
tbody tr.student{background:#15291f}
tbody tr.student:hover{background:#1a3427}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11.5px}
.tag.remote{background:#13273f;color:var(--acc)}
.tag.black{background:#3a1f24;color:var(--red)}
.tag.cat{background:#20301f;color:var(--green)}
.tag.onsite{background:#33280f;color:var(--amber)}
.money{color:var(--green);font-weight:600;white-space:nowrap}
.dim{color:var(--dim)}
.detail{height:240px;border-top:1px solid var(--line);background:var(--panel);display:flex}
.detail .info{flex:1.4;overflow:auto;padding:14px 18px}
.detail .log{flex:1;border-left:1px solid var(--line);overflow:auto;padding:14px 18px;font-family:Consolas,monospace;font-size:12px;color:var(--dim);white-space:pre-wrap}
.detail h3{font-size:15px;margin-bottom:8px}
.detail .meta{color:var(--dim);font-size:12.5px;margin-bottom:8px;display:flex;gap:16px;flex-wrap:wrap}
.detail .desc{white-space:pre-wrap;font-size:13px;color:#c3cedb}
.btns{display:flex;gap:8px;margin:10px 0}
.empty{padding:60px;text-align:center;color:var(--dim)}
</style>
</head>
<body>
<header>
  <h1>猿急送兼职项目智能筛选系统</h1>
  <span class="sub">读取 · 重新爬取 · 搜索 · 筛选 · 分类 · 导出</span>
</header>

<div class="toolbar">
  <button class="primary" onclick="reloadData()">↻ 读取/刷新数据</button>
  <label>页数 <input id="pages" type="number" min="1" style="width:64px" placeholder="全量"></label>
  <label>并发 <input id="conc" type="number" min="1" value="5" style="width:52px"></label>
  <label><input type="checkbox" id="fresh"> 清空重爬</label>
  <button id="scrapeBtn" class="primary" onclick="startScrape()">▶ 重新爬取</button>
  <span style="width:14px"></span>
  <button onclick="runClassify()">⚡ 智能分类</button>
  <button onclick="exportFull()">🗂 导出全部Excel</button>
  <button onclick="exportView()">📄 导出当前视图</button>
</div>

<div class="filters">
  <label>搜索 <input id="kw" placeholder="关键词（空格分隔多词）" style="width:230px" oninput="onFilter()"></label>
  <label>分类 <select id="cat" onchange="onFilter()"><option>全部</option></select></label>
  <label>预算 <input id="bmin" type="number" min="0" style="width:70px" placeholder="≥"> —
             <input id="bmax" type="number" min="0" style="width:70px" placeholder="≤"></label>
  <label><input type="checkbox" id="remote" onchange="onFilter()"> 仅远程</label>
  <label><input type="checkbox" id="noblack" checked onchange="onFilter()"> 排除黑名单</label>
  <label><input type="checkbox" id="student" onchange="onStudent()"> 学生模式(≤500元·非驻场)</label>
  <label>排序
    <select id="sort" onchange="onFilter()">
      <option>预算升序</option><option>预算降序</option>
      <option>投递人数升序</option><option>工时升序</option><option>最新优先</option>
    </select>
  </label>
  <button onclick="resetFilters()">重置</button>
</div>

<div class="stats" id="stats">加载中…</div>

<main>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th data-k="id">ID</th><th data-k="title">标题</th><th data-k="budget">预算</th>
        <th data-k="hours">工时</th><th data-k="work_type">类型</th>
        <th data-k="delivery_count">投递</th><th data-k="category">技术分类</th>
        <th>状态</th><th data-k="employer">雇主</th><th>描述摘要</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
    <div class="empty" id="empty" style="display:none">暂无数据，请点击「重新爬取」或调整筛选条件</div>
  </div>

  <div class="detail">
    <div class="info" id="detail"><h3>项目详情</h3><p class="dim">点击表格中任意一行查看完整信息；双击直接打开职位链接</p></div>
    <div class="log" id="logBox">爬取日志
（等待操作）</div>
  </div>
</main>

<script>
let ALL = [], VIEW = [], selectedId = null, pollTimer = null;

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const e = await r.json().catch(() => ({error: r.statusText}));
    throw new Error(e.error || r.statusText);
  }
  return r.json();
}

function fail(e, tag) { log("[" + tag + "] " + e.message); alert(e.message); }

async function reloadData() {
  try {
    const d = await api("/api/data");
    ALL = d.projects;
    const sel = $("cat"), cur = sel.value;
    sel.innerHTML = d.categories.map(c => `<option>${esc(c)}</option>`).join("");
    if (d.categories.includes(cur)) sel.value = cur;
    onFilter();
    setStats(d.summary);
  } catch (e) { fail(e, "load"); }
}

function onStudent() {
  if ($("student").checked) $("noblack").checked = true;
  onFilter();
}

function onFilter() {
  const kw = $("kw").value.trim().toLowerCase();
  const terms = kw ? kw.split(/\s+/) : [];
  const cat = $("cat").value, bmin = +$("bmin").value || 0, bmax = +$("bmax").value || 0;
  const remote = $("remote").checked, noblack = $("noblack").checked, student = $("student").checked;
  const sort = $("sort").value;

  VIEW = ALL.filter(p => {
    if (student) {
      if (p.blacklist_hit || p.budget <= 0 || p.budget > 500 || p.is_onsite) return false;
    } else if (noblack && p.blacklist_hit) return false;
    if (terms.length) {
      const hay = (p.title + " " + p.work_type + " " + p.desc + " " + p.employer + " " + p.category).toLowerCase();
      if (!terms.every(t => hay.includes(t))) return false;
    }
    if (cat !== "全部" && p.category !== cat) return false;
    if (bmin > 0 && p.budget < bmin) return false;
    if (bmax > 0 && (p.budget <= 0 || p.budget > bmax)) return false;
    if (remote && !p.is_remote) return false;
    return true;
  });

  const invalid = p => p.budget <= 0;
  if (sort === "预算升序") VIEW.sort((a,b) => (invalid(a)-invalid(b)) || a.budget-b.budget || a.delivery_count-b.delivery_count);
  else if (sort === "预算降序") VIEW.sort((a,b) => (invalid(a)-invalid(b)) || b.budget-a.budget);
  else if (sort === "投递人数升序") VIEW.sort((a,b) => a.delivery_count-b.delivery_count || a.budget-b.budget);
  else if (sort === "工时升序") VIEW.sort((a,b) => (parseFloat(a.hours)-parseFloat(b.hours)));
  else if (sort === "最新优先") VIEW.sort((a,b) => +b.id - +a.id);

  render();
  const remoteN = VIEW.filter(p=>p.is_remote).length;
  const studentN = VIEW.filter(p=>!p.blacklist_hit && p.budget>0 && p.budget<=500 && !p.is_onsite).length;
  setStats(`共 <b>${ALL.length}</b> 条 · 显示 <b>${VIEW.length}</b> 条 · 远程 <b>${remoteN}</b> · 学生友好 <b>${studentN}</b> 条`);
}

function setStats(html) { $("stats").innerHTML = html; }

function render() {
  const tb = $("tbody");
  const student = $("student").checked;
  const frag = [];
  for (const p of VIEW.slice(0, 3000)) {
    const cls = [student ? "student" : "", p.id === selectedId ? "selected" : ""].join(" ");
    const status = p.blacklist_hit
      ? `<span class="tag black" title="命中：${esc(p.blacklist_word)}">${esc(p.blacklist_hit)}</span>`
      : (p.is_onsite ? `<span class="tag onsite">驻场</span>` : `<span class="tag remote">远程</span>`);
    frag.push(`<tr class="${cls}" data-id="${p.id}" onclick="showDetail('${p.id}')" ondblclick="openLink('${p.id}')">
      <td class="dim">${p.id}</td>
      <td><b>${esc(p.title)}</b></td>
      <td class="money">¥${p.budget}</td>
      <td>${esc(p.hours)}</td>
      <td class="dim">${esc(p.work_type)}</td>
      <td style="text-align:center">${p.delivery_count}</td>
      <td>${p.category && p.category !== "其他" ? `<span class="tag cat">${esc(p.category)}</span>` : `<span class="dim">其他</span>`}</td>
      <td>${status}</td>
      <td class="dim">${esc(p.employer)}</td>
      <td class="dim">${esc(p.desc)}</td></tr>`);
  }
  tb.innerHTML = frag.join("");
  $("empty").style.display = VIEW.length ? "none" : "block";
}

async function showDetail(id) {
  selectedId = id;
  document.querySelectorAll("tr.selected").forEach(e => e.classList.remove("selected"));
  const row = document.querySelector(`tr[data-id="${id}"]`);
  if (row) row.classList.add("selected");
  const p = await api("/api/project/" + id);
  $("detail").innerHTML = `
    <h3>${esc(p.title)}　<span class="money">¥${p.budget}</span></h3>
    <div class="meta">
      <span>工时：${esc(p.hours)} ${esc(p.hours_unit)}</span>
      <span>类型：${esc(p.work_type)}</span>
      <span>投递：${p.delivery_count} 人</span>
      <span>分类：<span class="tag cat">${esc(p.category || "未分类")}</span></span>
      <span>雇主：${esc(p.employer_name)}</span>
      ${p.blacklist_hit ? `<span style="color:var(--red)">黑名单：${esc(p.blacklist_hit)}（${esc(p.blacklist_word)}）</span>` : ""}
    </div>
    <div class="btns">
      <button class="primary" onclick="window.open('${esc(p.url)}')">打开职位链接</button>
      <button onclick="copyText('${esc(p.url)}')">复制链接</button>
      <button onclick="copyText('${esc(p.title)}（¥${p.budget}） ${esc(p.url)}')">复制标题+预算</button>
    </div>
    <div class="desc">${esc(p.description)}</div>`;
}

function openLink(id) { window.open("/api/redirect/" + id); }

function copyText(t) { navigator.clipboard.writeText(t); }

document.querySelectorAll("thead th[data-k]").forEach(th => {
  th.onclick = () => {
    const map = {budget:["预算升序","预算降序"], delivery_count:["投递人数升序","最新优先"],
                 hours:["工时升序","预算升序"], id:["最新优先","预算升序"], title:["预算升序","预算降序"]};
    const k = th.dataset.k;
    if (map[k]) { const cur = $("sort").value; $("sort").value = cur === map[k][0] ? map[k][1] : map[k][0]; onFilter(); }
  };
});

function resetFilters() {
  ["kw","bmin","bmax"].forEach(i => $(i).value = "");
  $("cat").value = "全部"; $("remote").checked = false;
  $("noblack").checked = true; $("student").checked = false; $("sort").value = "预算升序";
  onFilter();
}

async function startScrape() {
  const pages = $("pages").value ? +$("pages").value : null;
  const conc = Math.max(1, +$("conc").value || 5);
  const fresh = $("fresh").checked;
  $("scrapeBtn").disabled = true;
  log("[start] 正在启动爬取…");
  try {
    const r = await api("/api/scrape", {method:"POST", headers:{"Content-Type":"application/json"},
                                        body: JSON.stringify({pages, concurrency: conc, fresh})});
    if (!r.started) {
      $("scrapeBtn").disabled = false;
      log("[scrape] " + r.error); alert(r.error);
      return;
    }
    if (!pollTimer) pollScrape();
  } catch (e) { $("scrapeBtn").disabled = false; fail(e, "scrape"); }
}

async function pollScrape() {
  try {
    const s = await api("/api/scrape/status");
    log(s.messages.join("\n"));
    if (s.running) { pollTimer = setTimeout(pollScrape, 800); }
    else {
      pollTimer = null; $("scrapeBtn").disabled = false;
      if (s.done) { await reloadData(); }
    }
  } catch (e) { pollTimer = null; $("scrapeBtn").disabled = false; }
}

async function runClassify() {
  try {
    const r = await api("/api/classify", {method:"POST"});
    log("[classify] " + JSON.stringify(r.summary));
    await reloadData();
  } catch (e) { fail(e, "classify"); }
}

async function exportFull() {
  try {
    const r = await api("/api/export/full", {method:"POST"});
    log("[export] " + r.paths.join("\n"));
    alert("已导出：\n" + r.paths.join("\n"));
  } catch (e) { fail(e, "export"); }
}

async function exportView() {
  try {
    const body = collectFilters();
    const r = await api("/api/export/view", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    log("[export] " + r.path);
    alert("已导出 " + r.count + " 条：\n" + r.path);
  } catch (e) { fail(e, "export"); }
}

function collectFilters() {
  return {keyword:$("kw").value, category:$("cat").value,
          budget_min:+$("bmin").value||0, budget_max:+$("bmax").value||0,
          remote_only:$("remote").checked, exclude_blacklist:$("noblack").checked,
          student_mode:$("student").checked, sort_by:$("sort").value};
}

function log(msg) {
  if (!msg) return;
  $("logBox").textContent = "爬取日志\n" + msg.split("\n").slice(-30).join("\n");
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
