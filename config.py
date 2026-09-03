# -*- coding: utf-8 -*-
"""全局配置：URL、并发、路径、筛选阈值、黑名单与分类词库。"""
from __future__ import annotations

from pathlib import Path

# ---------- 站点 ----------
BASE_URL = "https://www.yuanjisong.com"
JOB_LIST_URL = f"{BASE_URL}/job"                 # 第 1 页
JOB_PAGE_URL = f"{BASE_URL}/job/allcity/page{{page}}"  # 第 N 页

# ---------- 抓取 ----------
IMPERSONATE = "chrome131"   # curl_cffi 浏览器 TLS 指纹
CONCURRENCY = 5             # 并发页面数（实测 WAF 下稳定）
PAGE_TIMEOUT = 25           # 单页超时（秒）
PAGE_RETRIES = 3            # 单页重试次数
RETRY_BACKOFF = 2.0         # 重试退避基数（秒），指数递增
CHECKPOINT_EVERY = 10       # 每抓 N 页落一次盘（断点续爬）
REQUEST_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "cache-control": "no-cache",
    "referer": BASE_URL + "/",
    "upgrade-insecure-requests": "1",
}

# ---------- 代理池 ----------
PROXY_TEST_URL = BASE_URL + "/"
PROXY_TEST_TIMEOUT = 8
PROXY_FAIL_LIMIT = 3        # 连续失败 N 次拉黑
PROXY_RECOVER_SECONDS = 300 # 拉黑 N 秒后自动恢复
PROXY_POOL_SIZE = 20        # 每次补充代理的目标数量

# ---------- 学生筛选 ----------
STUDENT_MAX_BUDGET = 500    # 预算上限（元）
STUDENT_ALLOW_ONGOING = True  # 是否保留"招募中"项目

# ---------- 路径 ----------
ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"
DATA_JSON = OUTPUT_DIR / "projects.json"
STATE_JSON = OUTPUT_DIR / "state.json"
EXCEL_ALL = OUTPUT_DIR / "projects.xlsx"
EXCEL_STUDENT = OUTPUT_DIR / "student_projects.xlsx"

# ---------- 智能过滤黑名单（类别 -> 关键词） ----------
# 命中即排除，并记录类别与命中词，保证过滤可解释、可审计。
BLACKLIST: dict[str, tuple[str, ...]] = {
    "高难度": (
        "架构师", "系统架构", "架构设计", "技术专家", "资深专家",
        "底层开发", "驱动开发", "内核", "编译器", "高性能", "高并发",
        "分布式系统", "微服务治理", "数据库内核",
    ),
    "违规敏感": (
        "翻墙", "梯子", "vpn搭建", "科学上网", "刷单", "刷量", "刷评论",
        "赌博", "博彩", "彩票预测", "棋牌", "外挂", "辅助", "作弊",
        "爬取个人信息", "公民个人信息", "短信轰炸", "呼死你",
    ),
    "硬件IoT": (
        "嵌入式", "单片机", "stm32", "arduino", "树莓派", "raspberry",
        "pcb", "altium", "硬件设计", "电路设计", "fpga", "plc",
        "mqtt", "zigbee", "modbus", "传感器", "摄像头对接", "rtsp",
    ),
    "游戏开发": (
        "unity", "unreal", "ue4", "ue5", "cocos", "godot",
        "游戏开发", "游戏客户端", "游戏服务端", "游戏策划", "shader",
    ),
    "驻场 onsite": (
        "驻场", "坐班", "驻场开发", "现场办公",
    ),
}

# ---------- 技术分类（优先级从上到下，命中即归类） ----------
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("爬虫", (
        "爬虫", "爬取", "采集", "抓取", "spider", "scrapy", "数据抓取",
        "反爬", "抓包", "逆向", "js逆向",
    )),
    ("AI智能体", (
        "智能体", "agent", "ai智能体", "llm", "大模型", "大语言模型",
        "chatgpt", "gpt", "openai", "rag", "知识库问答", "ai客服",
        "nlp", "自然语言", "机器学习", "深度学习", "训练", "微调",
        "aigc", "文生图", "数字人", "语音识别", "ocr",
    )),
    ("小程序移动端", (
        "小程序", "微信小程序", "公众号开发", "uni-app", "uniapp", "taro",
        "android", "安卓", "ios", "app开发", "移动端", "apk", "flutter",
        "react native", "鸿蒙", "harmonyos",
    )),
    ("前端", (
        "前端", "vue", "react", "angular", "html", "css", "javascript",
        "typescript", "h5", "页面开发", "响应式", "webgl", "three.js",
        "可视化", "echarts", "antd", "ui组件", "切图",
    )),
    ("后端接口", (
        "后端", "接口开发", "api", "restful", "graphql", "微服务",
        "java", "spring", "springboot", "golang", "go语言", "node.js",
        "nodejs", "django", "flask", "fastapi", "laravel", "php",
        "数据库设计", "mysql", "postgresql", "redis", "mongodb",
        "管理系统", "后台开发", "服务端", "admin",
    )),
    ("Web全栈", (
        "全栈", "前后端", "网站开发", "官网", "建站", "web开发",
        "业务系统", "管理平台", "crm", "erp", "oa系统",
    )),
    ("测试质检", (
        "测试", "自动化测试", "功能测试", "性能测试", "接口测试",
        "selenium", "pytest", "jmeter", "postman", "测试用例",
        "质量管理", "验收测试", "兼容性测试",
    )),
    ("运维部署", (
        "运维", "部署", "docker", "kubernetes", "k8s", "ci/cd",
        "jenkins", "linux运维", "nginx", "服务器配置", "上云",
        "自动化运维", "devops",
    )),
    ("数据分析", (
        "数据分析", "数据处理", "数据清洗", "excel", "表格", "报表",
        "可视化大屏", "pandas", "数据统计", "etl", "数据入库",
    )),
    ("工具脚本", (
        "脚本", "自动化", "批量处理", "小工具", "工具开发", "插件",
        "浏览器插件", "油猴", "tampermonkey", "办公自动化", "rpa",
        "文件处理", "文档处理", "批量转换",
    )),
]
CATEGORY_OTHER = "其他"
ALL_SHEETS = [name for name, _ in CATEGORY_KEYWORDS] + [CATEGORY_OTHER]
