"""HTML page routes: all browser-facing GET endpoints that render templates."""

import importlib.util
import json
import os
import sys
import time
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from augur.config import get_config
from augur.workspace import get_workspace, resolve_landing_url
from dashboard.deps import _APP_START_TIME, get_registry, templates
from dashboard.routes.personas import _persona_meta

router = APIRouter()

_FINNHUB_BASE = "https://finnhub.io/api/v1"


@router.get("/", response_class=HTMLResponse, summary="首页仪表盘")
async def index(request: Request):
    landing = resolve_landing_url(get_workspace(), path="/")
    if landing:
        return RedirectResponse(url=landing, status_code=302)
    agent_count = len(get_registry().get_all())
    try:
        from augur.datasources import available_sources
        ds_count = len(available_sources())
    except Exception:
        ds_count = 2
    stats = [
        {"value": str(agent_count), "label": "虚拟投资大师", "icon": "users"},
        {"value": "6", "label": "共识加权层", "icon": "layers"},
        {"value": "40+", "label": "评分因子", "icon": "sliders"},
        {"value": str(ds_count), "label": "数据源链路", "icon": "database"},
    ]
    featured = [
        {"avatar": "🏦", "id": "buffett", "name": "Warren Buffett", "style": "价值 · 护城河", "desc": "寻找具有持久竞争优势的企业，以合理价格长期持有。FCF 和 ROE 是核心衡量标准。", "tag": "价值投资"},
        {"avatar": "📐", "id": "graham", "name": "Benjamin Graham", "style": "安全边际 · 烟蒂股", "desc": "只在具有显著安全边际时买入，PE<15、PB<1.5 是硬性门槛。", "tag": "深度价值"},
        {"avatar": "🚀", "id": "cathie_wood", "name": "Cathie Wood", "style": "颠覆性创新", "desc": "专注 AI、基因组、区块链等颠覆性技术，接受高估值换取指数级成长。", "tag": "成长投资"},
        {"avatar": "🇨🇳", "id": "duan_yongping", "name": "段永平", "style": "本分 · 极度集中", "desc": "「本分」哲学：只做正确的事，停止做错误的事。极度集中持仓，能力圈内重仓。", "tag": "中国价值"},
    ]
    return templates.TemplateResponse(request=request, name="index.html", context={
        "title": "Augur — 投资大师仪表盘",
        "agent_count": agent_count,
        "stats": stats,
        "featured": featured,
    })


@router.get("/personas", response_class=HTMLResponse, summary="投资人人格系统页面")
async def personas_page(request: Request):
    return templates.TemplateResponse(request=request, name="personas.html", context={
        "personas": _persona_meta(),
        "title": "投资人人格系统",
    })


@router.get("/stocks", response_class=HTMLResponse, summary="股票分析页面")
async def stocks_page(request: Request):
    quick_tickers = ["AAPL", "NVDA", "MSFT", "GOOGL", "TSLA", "BRK.B", "META", "AMZN", "PDD", "BIDU"]
    return templates.TemplateResponse(request=request, name="stocks.html", context={
        "title": "股票分析",
        "quick_tickers": quick_tickers,
    })


@router.get("/signals", response_class=HTMLResponse, summary="信号监控页面")
async def signals_page(request: Request):
    return templates.TemplateResponse(request=request, name="signals.html", context={
        "title": "信号监控",
    })


@router.get("/scanner", response_class=HTMLResponse, summary="市场扫描器页面")
async def scanner_page(request: Request):
    return templates.TemplateResponse(request=request, name="scanner.html", context={
        "title": "市场扫描器 - Scanner",
    })


V2_PAGES = {
    "radar": {
        "title": "市场雷达",
        "heading": "市场雷达",
        "description": "参考 SpikePanel 的市场情报看板，用于汇总自选股、因子信号、新闻热度、Reddit 热度、X 关注度和期权资金流。",
        "mode_label": "框架占位",
        "guardrail": "这个页面目前只是版本 2.0 入口，不会自动抓取 X、Reddit、Google News、TradingAgents 或实时行情。",
        "cards": [
            {"title": "信号表", "body": "密集展示标的、评分、市场变化、来源数量和数据新鲜度。", "bullets": ["价格与趋势", "新闻数量", "情绪标签", "来源凭证"], "wide": True},
            {"title": "数据源状态", "body": "每个数据源都会显示空闲、运行中、失败或限流状态。", "bullets": ["市场", "新闻", "Reddit", "X / Twitter"]},
            {"title": "手动刷新", "body": "刷新保持由你手动控制，并限制标的数量和来源条数。", "bullets": ["最多标的数", "最多标题数", "冷却时间"]},
        ],
    },
    "sentiment": {
        "title": "市场情绪",
        "heading": "市场情绪",
        "description": "受控查看 X、Reddit 和新闻语气，默认不启动任何爬取。",
        "mode_label": "数据源未启用",
        "guardrail": "社交与新闻数据源都需要主动启用；页面会先显示配置状态，再发起外部请求。",
        "cards": [
            {"title": "X / Twitter", "body": "配置 API 后跟踪指定 KOL、股票标签和可信来源帖子。", "bullets": ["股票标签搜索", "KOL 观察名单", "来源链接"]},
            {"title": "Reddit", "body": "汇总 subreddit 活跃度、提及次数和热门帖子，并显示限流状态。", "bullets": ["提及次数", "热门帖子", "限流状态"]},
            {"title": "情绪评分", "body": "情绪评分与估值、市场因素分开展示，避免页面变成黑箱。", "bullets": ["看多", "看空", "分歧", "无数据"]},
        ],
    },
    "news-flow": {
        "title": "新闻流",
        "heading": "新闻流",
        "description": "Google News 标题、公司新闻和事件流，并保留来源凭证。",
        "mode_label": "RSS 未连接",
        "guardrail": "新闻刷新会缓存并限制数量；当前框架没有后台轮询。",
        "cards": [
            {"title": "Google News", "body": "围绕标的聚合标题，并展示来源、时间和链接凭证。", "bullets": ["标的查询", "行业查询", "宏观查询"]},
            {"title": "事件聚类", "body": "把重复标题合并成同一事件，保持页面可读。", "bullets": ["财报", "指引", "监管", "产品"]},
            {"title": "AI 摘要", "body": "摘要会引用来源标题，并保持可选。", "bullets": ["事实优先", "不做建议", "可追溯"]},
        ],
    },
    "research-memo": {
        "title": "研报笔记",
        "heading": "研报笔记",
        "description": "把 TradingAgents General+ 的分析维度压缩成可读的 PM 备忘录。",
        "mode_label": "仅手动分析",
        "guardrail": "TradingAgents 不会自动运行；必须手动点击、选择标的，并显示运行状态。",
        "cards": [
            {"title": "七个分析维度", "body": "市场、情绪、新闻、基本面、宏观、资金流和催化剂会成为备忘录章节。", "bullets": ["质量门控", "多空辩论", "PM 备忘录"], "wide": True},
            {"title": "数据缺口", "body": "缺少 Reddit、宏观或研报数据时会降低置信度，不假装确定。", "bullets": ["NO_DATA", "被限流", "未配置"]},
            {"title": "输出", "body": "最终备忘录保持紧凑：方向、置信度、核心论点、验证点、否定点和观察项。"},
        ],
    },
    "macro": {
        "title": "宏观面",
        "heading": "宏观监控",
        "description": "跟踪利率、通胀、大宗商品、美元、央行和行业风格环境。",
        "mode_label": "快照框架",
        "guardrail": "宏观数据源设计为低频刷新，不会阻塞仪表盘。",
        "cards": [
            {"title": "环境面板", "body": "紧凑展示利率、美元、油价、收益率、通胀和风险偏好。", "bullets": ["每日缓存", "事件标记", "行业影响"]},
            {"title": "标的影响", "body": "把宏观压力映射到标的和行业，但不做黑箱分数。", "bullets": ["顺风", "逆风", "中性"]},
            {"title": "数据源健康度", "body": "FRED 或其他宏观数据源失败时，会在运行状态里明确显示。"},
        ],
    },
    "trading-lab": {
        "title": "交易实验室",
        "heading": "交易实验室",
        "description": "TradingView、K 线测试、Brooks price action 标签和画线实验。",
        "mode_label": "无实时流",
        "guardrail": "该页面只在打开时加载，不会从主仪表盘启动实时行情流。",
        "cards": [
            {"title": "TradingView", "body": "能嵌入就嵌入；否则用当前标的和周期打开 TradingView。", "bullets": ["嵌入降级", "外部打开", "不强制登录"]},
            {"title": "K 线层", "body": "先准备 OHLCV 和画线接口，再选择实时数据源。", "bullets": ["周期", "支撑/阻力", "趋势线"], "wide": True},
            {"title": "Brooks 价格行为", "body": "后续标注趋势、震荡、突破、回踩、楔形和信号 K。"},
        ],
    },
    "technical-analysis": {
        "title": "技术面分析",
        "heading": "技术面分析",
        "description": "TradingView 图表 + agent 式技术面研判报告，覆盖行情、均线、MACD、RSI、布林带、VWMA、支撑阻力、市场规则、SPY/QQQ 大盘背景和风险指数。",
        "mode_label": "TradingView 图表",
        "guardrail": "页面打开时只加载 TradingView 图表。DeepSeek 研判必须手动触发，且需要 DEEPSEEK_API_KEY。",
        "cards": [
            {"title": "基础行情", "body": "收盘价、涨跌幅、阶段涨跌、5/20日均量、量比和量价背离提示。", "bullets": ["收盘价", "涨跌幅", "量比"]},
            {"title": "技术指标", "body": "均线、MACD、RSI、布林带、VWMA 逐项拆解，保留多空信号和技术含义。", "bullets": ["EMA/SMA", "MACD", "RSI", "BOLL", "VWMA"], "wide": True},
            {"title": "大盘共振", "body": "SPY/QQQ 与主标的放在同一套趋势框架里判断，避免只看个股。", "bullets": ["SPY", "QQQ", "趋势共振"]},
        ],
    },
    "runtime": {
        "title": "运行状态",
        "heading": "运行状态",
        "description": "可见的控制室，用来查看端口、数据源、缓存新鲜度和任务状态。",
        "mode_label": "本地服务可见",
        "guardrail": "所有重任务在允许运行前都要先在这里变得可见。",
        "cards": [
            {"title": "本地服务", "body": "显示当前仪表盘端口、进程、运行时间和最近错误。", "bullets": ["端口 8000", "uvicorn", "最近健康检查"]},
            {"title": "数据源", "body": "每个外部数据源都会显示状态和错误原因。", "bullets": ["已禁用", "空闲", "运行中", "失败", "被限流"], "wide": True},
            {"title": "控制项", "body": "后续控制项会支持停止任务、清理缓存和设置刷新限制。"},
        ],
    },
}


V2_PAGE_STATE = {
    "radar": {
        "sources": [
            {"name": "市场快照", "status": "degraded", "mode": "REST 降级", "limit": "60 秒刷新"},
            {"name": "新闻热度", "status": "已禁用", "mode": "手动", "limit": "最多 50 条标题"},
            {"name": "社交热度", "status": "已禁用", "mode": "手动", "limit": "最多 25 条帖子"},
            {"name": "期权 / 资金流", "status": "计划中", "mode": "手动", "limit": "待确认数据源"},
        ],
        "controls": ["选择自选股", "刷新快照", "打开来源凭证", "导出备忘录输入"],
        "next_steps": ["先选择第一批标的", "确认数据源", "设置单次刷新限制"],
    },
    "sentiment": {
        "sources": [
            {"name": "X / Twitter KOL 账号", "status": "未配置", "mode": "手动", "limit": "需要 API key"},
            {"name": "Reddit 帖子", "status": "未配置", "mode": "手动", "limit": "需要 API key"},
            {"name": "Google News 语气", "status": "已禁用", "mode": "优先缓存", "limit": "最多 50 条标题"},
        ],
        "controls": ["编辑 KOL 列表", "编辑 subreddit 列表", "刷新情绪数据", "查看原始凭证"],
        "next_steps": ["确认 KOL 账号", "确认 subreddit", "选择情绪模型"],
    },
    "news-flow": {
        "sources": [
            {"name": "Google News", "status": "已禁用", "mode": "手动", "limit": "RSS / 查询限制"},
            {"name": "公司新闻", "status": "已禁用", "mode": "手动", "limit": "按标的限制"},
            {"name": "宏观标题", "status": "已禁用", "mode": "手动", "limit": "按主题限制"},
        ],
        "controls": ["拉取新闻标题", "合并重复标题", "固定重要事件"],
        "next_steps": ["选择 RSS / 查询路径", "设置缓存时间", "定义事件分类"],
    },
    "research-memo": {
        "sources": [
            {"name": "市场面", "status": "degraded", "mode": "手动", "limit": "按标的限定"},
            {"name": "情绪面", "status": "已禁用", "mode": "手动", "limit": "按来源限定"},
            {"name": "新闻面", "status": "已禁用", "mode": "手动", "limit": "限制标题数量"},
            {"name": "宏观面", "status": "已禁用", "mode": "手动", "limit": "每日缓存"},
            {"name": "TradingAgents General+", "status": "手动", "mode": "显式手动运行", "limit": "用户确认后运行"},
        ],
        "controls": ["选择标的", "运行质量门控", "生成 PM 备忘录", "查看多空辩论"],
        "next_steps": ["接入备忘录结构", "加入置信度评分", "加入否定点清单"],
    },
    "macro": {
        "sources": [
            {"name": "利率", "status": "已禁用", "mode": "每日缓存", "limit": "低频刷新"},
            {"name": "大宗商品", "status": "degraded", "mode": "REST 降级", "limit": "60 秒刷新"},
            {"name": "美元 / 外汇", "status": "计划中", "mode": "每日缓存", "limit": "待确认数据源"},
            {"name": "央行", "status": "计划中", "mode": "手动", "limit": "仅事件触发"},
        ],
        "controls": ["刷新宏观环境面板", "映射标的影响", "查看宏观风险"],
        "next_steps": ["选择宏观数据源", "设置每日缓存路径", "定义行业映射"],
    },
    "trading-lab": {
        "sources": [
            {"name": "TradingView", "status": "外部加载", "mode": "按需打开", "limit": "无本地实时流"},
            {"name": "K 线测试数据", "status": "计划中", "mode": "手动", "limit": "受限 OHLCV"},
            {"name": "画线层", "status": "计划中", "mode": "仅本地", "limit": "仅当前页面"},
            {"name": "Brooks 标签", "status": "计划中", "mode": "手动", "limit": "测试模式"},
        ],
        "controls": ["打开 TradingView", "加载 K 线样本", "画线", "标记价格行为"],
        "next_steps": ["选择图表库", "确认实时数据源", "定义画线保存方式"],
    },
    "technical-analysis": {
        "sources": [
            {"name": "TradingView 图表组件", "status": "外部加载", "mode": "页面加载时", "limit": "仅此页面"},
            {"name": "指标逻辑", "status": "已就绪", "mode": "本地规则", "limit": "不调用 API"},
            {"name": "SPY / QQQ 大盘背景", "status": "计划中", "mode": "TradingView 图表", "limit": "手动刷新"},
            {"name": "DeepSeek 研判报告", "status": "未配置", "mode": "手动提交", "limit": "需要 API key"},
        ],
        "controls": ["加载 TradingView 图表", "打开 TradingView", "运行 DeepSeek 报告", "查看支撑 / 阻力"],
        "next_steps": ["接入 TradingView MCP 指标值", "保存指标快照", "加入券商 / 市场规则配置"],
    },
    "runtime": {
        "sources": [
            {"name": "本地进程", "status": "运行中", "mode": "只读", "limit": "仅本地"},
            {"name": "数据源注册表", "status": "手动", "mode": "只读", "limit": "不启动任务"},
            {"name": "缓存健康度", "status": "计划中", "mode": "只读", "limit": "本地文件"},
        ],
        "controls": ["刷新状态", "查看数据源配置", "停止后续任务", "清理选中缓存"],
        "next_steps": ["加入任务注册表", "加入缓存清单", "加入停止按钮"],
    },
}


STATUS_LABELS = {
    "ok": "正常",
    "available": "可用",
    "missing": "缺失",
    "configured": "已配置",
    "unconfigured": "未配置",
    "disabled": "已禁用",
    "degraded": "数据降级",
    "manual": "手动",
    "planned": "计划中",
    "external": "外部加载",
    "ready": "已就绪",
    "running": "运行中",
    "failed": "失败",
}


def _status_label(status: object) -> str:
    value = str(status or "unknown")
    return STATUS_LABELS.get(value, value)


def _with_status_labels(state: dict) -> dict:
    payload = dict(state or {})
    payload["sources"] = [
        {**source, "status_label": _status_label(source.get("status"))}
        for source in payload.get("sources", [])
    ]
    return payload


class TechnicalDeepSeekBody(BaseModel):
    symbol: str = Field(default="NASDAQ:NVDA", max_length=40)
    timeframe: str = Field(default="D", max_length=8)
    market_profile: str = Field(default="US", max_length=20)
    metrics: dict = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)


def _v2_context(page_id: str) -> dict:
    page = V2_PAGES[page_id]
    state = _with_status_labels(V2_PAGE_STATE.get(page_id, {}))
    return {"page_id": page_id, "state": state, **page}


def _v2_state_payload(page_id: str) -> dict:
    if page_id not in V2_PAGES:
        raise HTTPException(status_code=404, detail="Unknown version 2.0 page")
    return {
        "page_id": page_id,
        "title": V2_PAGES[page_id]["title"],
        "mode": V2_PAGES[page_id]["mode_label"],
        "guardrail": V2_PAGES[page_id]["guardrail"],
        **_with_status_labels(V2_PAGE_STATE.get(page_id, {})),
    }


@router.get("/api/v2/pages/{page_id}/state", summary="Version 2.0 page state")
async def api_v2_page_state(page_id: str):
    """Return page-level planning state without starting external providers."""
    return JSONResponse(content=_v2_state_payload(page_id))


@router.get("/api/v2/pages", summary="Version 2.0 page registry")
async def api_v2_pages():
    """Return the current version 2.0 page registry for lightweight clients."""
    return JSONResponse(content={
        "pages": [
            {"id": page_id, "title": page["title"], "mode": page["mode_label"]}
            for page_id, page in V2_PAGES.items()
        ]
    })


def _deepseek_status() -> dict:
    configured = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
    return {
        "name": "DeepSeek",
        "status": "configured" if configured else "未配置",
        "detail": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash") if configured else "设置 DEEPSEEK_API_KEY 后启用",
    }


def _technical_prompt(body: TechnicalDeepSeekBody) -> str:
    return f"""请生成中文技术面分析报告的结构化 JSON，报告只作为研究参考，不构成投资建议。

标的：{body.symbol}
周期：{body.timeframe}
市场类型：{body.market_profile}
用户补充/已知指标：{body.metrics}
备注：{body.notes}

只返回 JSON，不要返回 Markdown、代码围栏或解释文字。JSON 必须兼容这个结构：
{{
  "status": "ok",
  "symbol": "{body.symbol}",
  "market_profile": "{body.market_profile}",
  "snapshot": {{"source": "DeepSeek structured layer", "as_of": "YYYY-MM-DD"}},
  "risk": {{"score": 0-100, "label": "低/中/偏高/高/极高"}},
  "sections": {{
    "basic": [{{"item": "最新收盘价", "value": "199.18 (2026-07-24)", "meaning": "技术分析基准价"}}],
    "indicator_details": [
      {{
        "title": "均线系统（空头排列，死叉格局）",
        "table": [{{"indicator": "10日EMA", "value": "226.00", "signal": "短期空头"}}],
        "points": ["价格远低于 10EMA 和 50SMA，属于严重偏离均线的超跌状态。"]
      }}
    ],
    "support": [{{"level": "第一支撑", "price": "196.98", "basis": "日内低点"}}],
    "resistance": [{{"level": "第一阻力", "price": "226.00", "basis": "10日EMA"}}],
    "market_rules": [{{"rule": "A股 T+1", "impact": "盘中抄底当日无法卖出，需要承受隔夜风险"}}],
    "backdrop": [{{"symbol": "SPY", "trend": "走强/转弱/待确认", "status": "大盘过滤结论"}}],
    "summary": {{
      "core": "核心判断",
      "bearish": ["看空证据"],
      "bullish": ["潜在积极信号"],
      "watch": ["观察条件"]
    }},
    "signals": [{{"indicator": "MACD", "value": "-6.44", "signal": "空", "meaning": "死叉运行，空头动能强化"}}]
  }}
}}

要求：
- 不要编造没有提供的精确价格或指标值；没有数据时写“待接入/暂无数据”。
- 可以给出判断框架、观察条件和风险等级，但不要给个性化买卖指令。
- 风格参考专业 agent 报告：结构化、表格化、直接指出多空证据和风险。
- 如果 body.metrics.generated_report 已经有 sections，请在它的基础上补全 indicator_details 和文字解释，不要改变真实数值。"""


def _parse_llm_json(content: str) -> dict | None:
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _tv_to_data_symbol(symbol: str) -> str:
    value = (symbol or "NASDAQ:NVDA").strip().upper()
    if ":" in value:
        value = value.split(":", 1)[1]
    return value.replace("/", ".")


def _safe_num(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _round(value: float, places: int = 2) -> float:
    return round(_safe_num(value), places)


def _sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    window = values[-period:] if len(values) >= period else values
    return sum(window) / len(window)


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    series = [values[0]]
    for value in values[1:]:
        series.append((value * alpha) + (series[-1] * (1 - alpha)))
    return series


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(values: list[float]) -> dict:
    if len(values) < 26:
        return {"dif": 0.0, "dea": 0.0, "hist": 0.0, "prev_hist": 0.0}
    ema12 = _ema_series(values, 12)
    ema26 = _ema_series(values, 26)
    dif_series = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    dea_series = _ema_series(dif_series, 9)
    hist = dif_series[-1] - dea_series[-1]
    prev_hist = (dif_series[-2] - dea_series[-2]) if len(dif_series) > 1 and len(dea_series) > 1 else hist
    return {"dif": dif_series[-1], "dea": dea_series[-1], "hist": hist, "prev_hist": prev_hist}


def _bollinger(values: list[float], period: int = 20) -> dict:
    if not values:
        return {"upper": 0.0, "middle": 0.0, "lower": 0.0}
    window = values[-period:] if len(values) >= period else values
    middle = sum(window) / len(window)
    variance = sum((v - middle) ** 2 for v in window) / len(window)
    std = variance ** 0.5
    return {"upper": middle + 2 * std, "middle": middle, "lower": middle - 2 * std}


def _vwma(closes: list[float], volumes: list[float], period: int = 20) -> float:
    if not closes or not volumes:
        return 0.0
    c_window = closes[-period:]
    v_window = volumes[-period:]
    total_volume = sum(v_window)
    if total_volume <= 0:
        return _sma(c_window, len(c_window))
    return sum(c * v for c, v in zip(c_window, v_window)) / total_volume


def _fetch_finnhub_bars(symbol: str, days: int = 330) -> tuple[list[dict], str]:
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return [], "FINNHUB_API_KEY 未配置"
    data_symbol = _tv_to_data_symbol(symbol)
    end = int(datetime.now(timezone.utc).timestamp())
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    params = urllib.parse.urlencode({
        "symbol": data_symbol,
        "resolution": "D",
        "from": str(start),
        "to": str(end),
        "token": api_key,
    })
    url = f"{_FINNHUB_BASE}/stock/candle?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "augur-technical/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return [], f"Finnhub candle 请求失败：{exc}"
    if payload.get("s") != "ok":
        return [], f"Finnhub 无可用日线数据：{payload.get('s', 'unknown')}"
    rows = []
    for idx, close in enumerate(payload.get("c", [])):
        rows.append({
            "time": payload.get("t", [])[idx],
            "date": datetime.fromtimestamp(payload.get("t", [])[idx], timezone.utc).strftime("%Y-%m-%d"),
            "open": _safe_num(payload.get("o", [])[idx]),
            "high": _safe_num(payload.get("h", [])[idx]),
            "low": _safe_num(payload.get("l", [])[idx]),
            "close": _safe_num(close),
            "volume": _safe_num(payload.get("v", [])[idx]),
        })
    return [row for row in rows if row["close"] > 0], "finnhub"


def _fetch_finnhub_quote(symbol: str) -> tuple[dict, str]:
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return {}, "FINNHUB_API_KEY 未配置"
    data_symbol = _tv_to_data_symbol(symbol)
    params = urllib.parse.urlencode({"symbol": data_symbol, "token": api_key})
    url = f"{_FINNHUB_BASE}/quote?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "augur-technical/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {}, f"Finnhub quote 请求失败：{exc}"
    close = _safe_num(payload.get("c"))
    prev_close = _safe_num(payload.get("pc"))
    if close <= 0:
        return {}, "Finnhub quote 无当前价"
    timestamp = _safe_num(payload.get("t"))
    as_of = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d") if timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "close": close,
        "prev_close": prev_close,
        "open": _safe_num(payload.get("o")),
        "high": _safe_num(payload.get("h")),
        "low": _safe_num(payload.get("l")),
        "day_change_pct": _safe_num(payload.get("dp")),
        "as_of": as_of,
    }, "finnhub_quote"


def _signal(label: str, polarity: str, meaning: str) -> dict:
    return {"label": label, "signal": polarity, "meaning": meaning}


def _trend_from_metrics(metrics: dict) -> str:
    close = metrics["close"]
    ema10 = metrics["ema10"]
    sma50 = metrics["sma50"]
    sma200 = metrics["sma200"]
    if close > ema10 > sma50 > sma200:
        return "走强"
    if close < ema10 < sma50 and (sma200 <= 0 or sma50 < sma200):
        return "转弱"
    return "震荡"


def _build_technical_snapshot(symbol: str) -> dict:
    bars, source = _fetch_finnhub_bars(symbol)
    if len(bars) < 30:
        quote, quote_source = _fetch_finnhub_quote(symbol)
        if quote:
            return {
                "symbol": symbol,
                "status": "quote_only",
                "source": quote_source,
                "bars": len(bars),
                "as_of": quote["as_of"],
                "metrics": {key: _round(value, 4) if isinstance(value, (int, float)) else value for key, value in quote.items()},
                "trend": "待 K 线确认",
                "error": f"{source}；已降级到实时 quote",
            }
        return {"symbol": symbol, "status": "degraded", "source": source, "bars": len(bars), "error": source}
    closes = [row["close"] for row in bars]
    highs = [row["high"] for row in bars]
    lows = [row["low"] for row in bars]
    volumes = [row["volume"] for row in bars]
    close = closes[-1]
    prev_close = closes[-2] if len(closes) > 1 else close
    day_change_pct = ((close / prev_close) - 1) * 100 if prev_close else 0.0
    start_24 = closes[-25] if len(closes) >= 25 else closes[0]
    change_24_pct = ((close / start_24) - 1) * 100 if start_24 else 0.0
    avg_vol_5 = sum(volumes[-5:]) / min(5, len(volumes))
    avg_vol_20 = sum(volumes[-20:]) / min(20, len(volumes))
    volume_ratio = avg_vol_5 / avg_vol_20 if avg_vol_20 else 0.0
    macd = _macd(closes)
    boll = _bollinger(closes)
    metrics = {
        "close": close,
        "prev_close": prev_close,
        "day_change_pct": day_change_pct,
        "change_24_pct": change_24_pct,
        "avg_vol_5": avg_vol_5,
        "avg_vol_20": avg_vol_20,
        "volume_ratio": volume_ratio,
        "ema10": _ema_series(closes, 10)[-1],
        "sma20": _sma(closes, 20),
        "sma50": _sma(closes, 50),
        "sma200": _sma(closes, 200),
        "rsi14": _rsi(closes),
        "macd_dif": macd["dif"],
        "macd_dea": macd["dea"],
        "macd_hist": macd["hist"],
        "macd_prev_hist": macd["prev_hist"],
        "boll_upper": boll["upper"],
        "boll_middle": boll["middle"],
        "boll_lower": boll["lower"],
        "vwma20": _vwma(closes, volumes, 20),
        "last_low": lows[-1],
        "recent_low": min(lows[-20:]),
        "recent_high": max(highs[-20:]),
    }
    return {
        "symbol": symbol,
        "status": "ok",
        "source": source,
        "as_of": bars[-1]["date"],
        "bars": len(bars),
        "metrics": {key: _round(value, 4) for key, value in metrics.items()},
        "trend": _trend_from_metrics(metrics),
    }


def _risk_score(snapshot: dict, spy: dict, qqq: dict) -> tuple[int, str]:
    if snapshot.get("status") == "quote_only":
        m = snapshot.get("metrics", {})
        score = 45
        if _safe_num(m.get("day_change_pct")) < -2:
            score += 12
        if _safe_num(m.get("day_change_pct")) > 2:
            score -= 5
        return max(0, min(100, score)), "中" if score < 55 else "偏高"
    if snapshot.get("status") != "ok":
        return 60, "偏高"
    m = snapshot["metrics"]
    score = 20
    if m["close"] < m["ema10"]:
        score += 10
    if m["ema10"] < m["sma50"]:
        score += 15
    if m["sma200"] and m["sma50"] < m["sma200"]:
        score += 10
    if m["macd_dif"] < m["macd_dea"]:
        score += 12
    if m["macd_hist"] < m["macd_prev_hist"]:
        score += 8
    if m["rsi14"] < 50:
        score += 8
    if m["rsi14"] > 75:
        score += 10
    if m["close"] < m["boll_middle"]:
        score += 8
    if m["volume_ratio"] > 1.1 and m["day_change_pct"] < 0:
        score += 12
    for index_snapshot in (spy, qqq):
        if index_snapshot.get("trend") == "转弱":
            score += 8
    score = max(0, min(100, int(score)))
    label = "低" if score < 30 else "中" if score < 50 else "偏高" if score < 70 else "高" if score < 85 else "极高"
    return score, label


def _build_technical_report(symbol: str, market_profile: str) -> dict:
    snapshot = _build_technical_snapshot(symbol)
    spy = _build_technical_snapshot("SPY")
    qqq = _build_technical_snapshot("QQQ")
    if snapshot.get("status") == "quote_only":
        m = snapshot["metrics"]
        risk_score, risk_label = _risk_score(snapshot, spy, qqq)
        day_change = _safe_num(m.get("day_change_pct"))
        direction = "下跌" if day_change < 0 else "上涨" if day_change > 0 else "平盘"
        backdrop = [
            {"symbol": "SPY", "trend": spy.get("trend", "暂无数据"), "status": spy.get("status", "degraded")},
            {"symbol": "QQQ", "trend": qqq.get("trend", "暂无数据"), "status": qqq.get("status", "degraded")},
        ]
        return {
            "status": "ok",
            "data_quality": "quote_only",
            "symbol": symbol,
            "market_profile": market_profile,
            "snapshot": snapshot,
            "spy": spy,
            "qqq": qqq,
            "risk": {"score": risk_score, "label": risk_label},
            "sections": {
                "basic": [
                    {"item": "最新价", "value": f"{m.get('close')} ({snapshot.get('as_of')})", "meaning": "来自 Finnhub quote"},
                    {"item": "当日涨跌幅", "value": f"{_round(day_change)}%", "meaning": f"前收 {m.get('prev_close')} -> 当前 {m.get('close')}"},
                    {"item": "日内区间", "value": f"{m.get('low')} - {m.get('high')}", "meaning": "仅当日高低点，非历史支撑阻力"},
                    {"item": "近24日累计涨跌幅", "value": "待 K 线数据源", "meaning": "当前 Finnhub key 无 candle 权限"},
                    {"item": "近5日/20日均量与量比", "value": "待 K 线数据源", "meaning": "需要 OHLCV 历史数据"},
                ],
                "indicators": [
                    _signal("均线系统", "待 K 线数据源", "10EMA/20MA/50SMA/200SMA 需要历史收盘价"),
                    _signal("MACD", "待 K 线数据源", "DIF/DEA/BAR 需要至少26个交易日"),
                    _signal("RSI(14)", "待 K 线数据源", "RSI 需要至少15个交易日"),
                    _signal("布林带", "待 K 线数据源", "BOLL 需要20日历史价格"),
                    _signal("VWMA", "待 K 线数据源", "VWMA 需要20日成交量"),
                ],
                "support": [
                    {"level": "日内低点", "price": m.get("low"), "basis": "Finnhub quote"},
                    {"level": "前收盘", "price": m.get("prev_close"), "basis": "短线参照"},
                    {"level": "历史支撑", "price": "待 K 线数据源", "basis": "需要近20-60日低点"},
                ],
                "resistance": [
                    {"level": "日内高点", "price": m.get("high"), "basis": "Finnhub quote"},
                    {"level": "历史阻力", "price": "待 K 线数据源", "basis": "需要均线、前高、VWMA"},
                ],
                "market_rules": [
                    {"rule": "A股", "impact": "涨跌停、T+1、换手率、连续跌停风险"},
                    {"rule": "美股", "impact": "无涨跌停、盘前盘后、财报跳空、期权波动"},
                    {"rule": "加密货币 / Crypto", "impact": "24/7 交易、杠杆清算、周末流动性"},
                ],
                "backdrop": backdrop,
                "summary": {
                    "core": f"当前只有实时 quote，价格当日{direction} {_round(day_change)}%；风险等级暂定 {risk_label} ({risk_score}/100)。完整趋势需接入 K 线数据源或 TradingView MCP。",
                    "bearish": ["历史技术指标暂不可用，不能确认是否空头排列", "若当日下跌幅度扩大，需等待 K 线和量能确认"],
                    "bullish": ["实时价格可用于日内观察", "后续接入 K 线后可补齐均线、MACD、RSI、BOLL、VWMA"],
                    "watch": ["接入 TradingView MCP 读取 OHLC/指标", "配置可用 candle 数据源", "观察是否突破日内高点/跌破日内低点", "结合 SPY/QQQ 背景过滤"],
                },
                "signals": [
                    {"indicator": "最新价", "value": m.get("close"), "signal": direction, "meaning": "实时 quote"},
                    {"indicator": "当日涨跌幅", "value": f"{_round(day_change)}%", "signal": "偏空" if day_change < 0 else "偏多" if day_change > 0 else "中性", "meaning": "当日方向"},
                    {"indicator": "10EMA/50SMA/200SMA", "value": "待 K 线数据源", "signal": "待判断", "meaning": "趋势结构"},
                    {"indicator": "MACD/RSI/BOLL/VWMA", "value": "待 K 线数据源", "signal": "待判断", "meaning": "动能、强弱、波动和量价"},
                    {"indicator": "SPY/QQQ", "value": f"{backdrop[0]['trend']} / {backdrop[1]['trend']}", "signal": "待确认", "meaning": "大盘共振过滤"},
                ],
            },
        }
    if snapshot.get("status") != "ok":
        return {
            "status": "degraded",
            "symbol": symbol,
            "message": snapshot.get("error", "暂无可用行情数据"),
            "snapshot": snapshot,
            "spy": spy,
            "qqq": qqq,
        }
    m = snapshot["metrics"]
    risk_score, risk_label = _risk_score(snapshot, spy, qqq)
    volume_signal = "下跌放量，抛压尚未衰竭" if m["day_change_pct"] < 0 and m["volume_ratio"] > 1.1 else "上涨放量，趋势得到成交确认" if m["day_change_pct"] > 0 and m["volume_ratio"] > 1.1 else "量能未明显放大，信号需观察"
    ma_signal = "空头排列" if m["close"] < m["ema10"] < m["sma50"] else "多头排列" if m["close"] > m["ema10"] > m["sma50"] else "均线纠缠"
    macd_signal = "死叉运行" if m["macd_dif"] < m["macd_dea"] else "金叉运行"
    rsi_signal = "超买风险" if m["rsi14"] > 70 else "偏弱但未超卖" if m["rsi14"] < 50 and m["rsi14"] > 30 else "超卖观察" if m["rsi14"] <= 30 else "健康强势"
    boll_signal = "跌破中轨，弱势运行" if m["close"] < m["boll_middle"] else "站上中轨，趋势改善"
    vwma_signal = "VWMA 在价格上方，成交密集区形成压制" if m["vwma20"] > m["close"] else "价格站上 VWMA，量价结构改善"
    support = [
        {"level": "第一支撑", "price": m["last_low"], "basis": "最近交易日低点"},
        {"level": "第二支撑", "price": m["recent_low"], "basis": "近20日低点"},
        {"level": "第三支撑", "price": round(m["close"] // 10 * 10, 2), "basis": "整数关口"},
    ]
    resistance = [
        {"level": "第一阻力", "price": m["ema10"], "basis": "10日 EMA"},
        {"level": "第二阻力", "price": m["sma50"], "basis": "50日 SMA"},
        {"level": "第三阻力", "price": m["boll_middle"], "basis": "布林带中轨"},
        {"level": "第四阻力", "price": m["vwma20"], "basis": "20日 VWMA"},
    ]
    backdrop = [
        {"symbol": "SPY", "trend": spy.get("trend", "暂无数据"), "status": spy.get("status", "degraded")},
        {"symbol": "QQQ", "trend": qqq.get("trend", "暂无数据"), "status": qqq.get("status", "degraded")},
    ]
    resonance = "强共振" if snapshot["trend"] == "走强" and spy.get("trend") == "走强" and qqq.get("trend") == "走强" else "系统性背离/降权" if snapshot["trend"] == "走强" and (spy.get("trend") == "转弱" or qqq.get("trend") == "转弱") else "弱共振"
    bearish = [
        "价格低于10EMA/50SMA，短中期趋势承压" if m["close"] < m["ema10"] and m["close"] < m["sma50"] else "短中期均线压力不明显",
        f"MACD {macd_signal}，柱状图 {'扩大' if m['macd_hist'] < m['macd_prev_hist'] else '收窄'}",
        f"RSI={_round(m['rsi14'])}，{rsi_signal}",
        f"量比={_round(m['volume_ratio'])}，{volume_signal}",
    ]
    bullish = [
        "价格偏离短中期均线较大，技术性反弹需求可能积累" if m["close"] < m["ema10"] and abs((m["close"] / m["ema10"] - 1) * 100) > 8 else "暂未出现明确超跌反弹条件",
        "MACD 柱状图开始收窄时可观察动能衰竭" if m["macd_hist"] < 0 else "MACD 仍在正值区，动能尚可",
        f"SPY/QQQ 背景：{backdrop[0]['trend']} / {backdrop[1]['trend']}，{resonance}",
    ]
    return {
        "status": "ok",
        "symbol": symbol,
        "market_profile": market_profile,
        "snapshot": snapshot,
        "spy": spy,
        "qqq": qqq,
        "risk": {"score": risk_score, "label": risk_label},
        "sections": {
            "basic": [
                {"item": "最新收盘价", "value": f"{m['close']} ({snapshot['as_of']})", "meaning": "技术分析基准价"},
                {"item": "当日涨跌幅", "value": f"{_round(m['day_change_pct'])}%", "meaning": f"前收 {m['prev_close']} -> {m['close']}"},
                {"item": "近24日累计涨跌幅", "value": f"{_round(m['change_24_pct'])}%", "meaning": "衡量中短期趋势深度"},
                {"item": "近5日平均成交量", "value": f"{int(m['avg_vol_5']):,}", "meaning": "短期成交强度"},
                {"item": "近20日平均成交量", "value": f"{int(m['avg_vol_20']):,}", "meaning": "中期成交基准"},
                {"item": "量比", "value": f"{_round(m['volume_ratio'])}x", "meaning": volume_signal},
            ],
            "indicators": [
                _signal("均线系统", ma_signal, f"10EMA={_round(m['ema10'])}, 50SMA={_round(m['sma50'])}, 200SMA={_round(m['sma200'])}"),
                _signal("MACD", macd_signal, f"DIF={_round(m['macd_dif'])}, DEA={_round(m['macd_dea'])}, BAR={_round(m['macd_hist'])}"),
                _signal("RSI(14)", rsi_signal, f"RSI={_round(m['rsi14'])}；50中轴用于强弱分界"),
                _signal("布林带", boll_signal, f"上轨={_round(m['boll_upper'])}, 中轨={_round(m['boll_middle'])}, 下轨={_round(m['boll_lower'])}"),
                _signal("VWMA", vwma_signal, f"VWMA20={_round(m['vwma20'])}"),
            ],
            "support": support,
            "resistance": resistance,
            "market_rules": [
                {"rule": "A股", "impact": "涨跌停、T+1、换手率、连续跌停风险"},
                {"rule": "美股", "impact": "无涨跌停、盘前盘后、财报跳空、期权波动"},
                {"rule": "加密货币 / Crypto", "impact": "24/7 交易、杠杆清算、周末流动性"},
            ],
            "backdrop": backdrop,
            "summary": {
                "core": f"{snapshot['trend']}；风险等级 {risk_label} ({risk_score}/100)；大盘状态 {resonance}",
                "bearish": bearish,
                "bullish": bullish,
                "watch": ["缩量止跌", "RSI 超卖后拐头", "MACD 柱体收窄", "放量阳线站上10EMA", "SPY/QQQ 同步企稳"],
            },
            "signals": [
                {"indicator": "收盘价", "value": m["close"], "signal": snapshot["trend"], "meaning": "价格相对均线结构"},
                {"indicator": "量比", "value": f"{_round(m['volume_ratio'])}x", "signal": "偏空" if "下跌放量" in volume_signal else "观察", "meaning": volume_signal},
                {"indicator": "10EMA", "value": _round(m["ema10"]), "signal": "空" if m["close"] < m["ema10"] else "多", "meaning": "短线趋势位"},
                {"indicator": "50SMA", "value": _round(m["sma50"]), "signal": "空" if m["close"] < m["sma50"] else "多", "meaning": "中线趋势位"},
                {"indicator": "MACD", "value": _round(m["macd_hist"]), "signal": "空" if macd_signal.startswith("死叉") else "多", "meaning": macd_signal},
                {"indicator": "RSI", "value": _round(m["rsi14"]), "signal": rsi_signal, "meaning": "强弱/超买超卖"},
                {"indicator": "BOLL 中轨", "value": _round(m["boll_middle"]), "signal": "空" if m["close"] < m["boll_middle"] else "多", "meaning": boll_signal},
                {"indicator": "VWMA", "value": _round(m["vwma20"]), "signal": "空" if m["close"] < m["vwma20"] else "多", "meaning": vwma_signal},
                {"indicator": "SPY/QQQ", "value": f"{backdrop[0]['trend']} / {backdrop[1]['trend']}", "signal": resonance, "meaning": "大盘共振过滤"},
            ],
        },
    }


@router.get("/api/v2/technical/status", summary="Technical analysis provider status")
async def api_v2_technical_status():
    return JSONResponse(content={
        "status": "ok",
        "providers": [
            {"name": "TradingView 图表组件", "status": "外部加载", "detail": "只在 /technical-analysis 页面由浏览器加载"},
            {"name": "TradingView MCP", "status": "手动", "detail": "Codex 可手动使用，但不是仪表盘后台任务"},
            _env_status("FINNHUB_API_KEY", "Finnhub quote/candle"),
            _deepseek_status(),
        ],
        "models": {
            "default": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        },
        "guardrails": [
            "只有用户点击运行时才请求 DeepSeek",
            "仪表盘不会自动读取 TradingView MCP",
            "没有隐藏后台轮询",
        ],
    })


@router.get("/api/v2/technical/report", summary="Generate technical analysis report")
def api_v2_technical_report(symbol: str = "NASDAQ:NVDA", market_profile: str = "US"):
    """Generate a bounded technical report from configured lightweight data sources."""
    return JSONResponse(content=_build_technical_report(symbol, market_profile))


@router.post("/api/v2/technical/deepseek-report", summary="Run manual DeepSeek technical report")
async def api_v2_technical_deepseek_report(body: TechnicalDeepSeekBody):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if not api_key:
        return JSONResponse(content={
            "status": "未配置",
            "model": model,
            "message": "DEEPSEEK_API_KEY 未配置。页面已就绪，但没有发送 AI 请求。",
        })
    try:
        import httpx
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是严谨的技术面研究助手。只基于给定数据和明确可验证的技术分析规则输出，不构成投资建议。"},
                        {"role": "user", "content": _technical_prompt(body)},
                    ],
                    "max_tokens": 3200,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        report_json = _parse_llm_json(content)
        if report_json:
            report_json.setdefault("status", "ok")
            report_json.setdefault("symbol", body.symbol)
            report_json.setdefault("market_profile", body.market_profile)
        return JSONResponse(content={
            "status": "ok",
            "model": model,
            "report": content,
            "report_json": report_json,
            "usage": data.get("usage", {}),
        })
    except Exception as exc:
        return JSONResponse(status_code=502, content={
            "status": "失败",
            "model": model,
            "message": f"DeepSeek 请求失败：{exc}",
        })


def _module_status(module_name: str, label: str, install_hint: str = "") -> dict:
    available = importlib.util.find_spec(module_name) is not None
    return {
        "name": label,
        "status": "available" if available else "missing",
        "detail": "已安装" if available else (install_hint or f"{module_name} 未安装"),
    }


def _env_status(env_name: str, label: str) -> dict:
    configured = bool(os.environ.get(env_name))
    return {
        "name": label,
        "status": "configured" if configured else "未配置",
        "detail": env_name if configured else f"设置 {env_name} 后启用",
    }


@router.get("/api/v2/runtime/status", summary="Version 2.0 runtime status")
async def api_v2_runtime_status(request: Request):
    """Return a lightweight local runtime snapshot.

    This endpoint is intentionally read-only: no external network calls, no
    background tasks, and no provider initialization.
    """
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    uptime_seconds = max(0, int(time.time() - _APP_START_TIME))
    modules = [
        _module_status("fastapi", "FastAPI"),
        _module_status("uvicorn", "Uvicorn"),
        _module_status("websockets", "WebSocket 传输", "安装 uvicorn[standard] 或 websockets"),
        _module_status("yfinance", "行情数据 / yfinance", "安装 augur-agents[data]"),
    ]
    providers = [
        {"name": "仪表盘", "status": "运行中", "detail": f"{request.url.scheme}://{request.url.hostname}:{port}"},
        {"name": "TradingAgents General+", "status": "手动", "detail": "未从仪表盘启动"},
        {"name": "Google News", "status": "已禁用", "detail": "仅数据源框架"},
        {"name": "Reddit", "status": "已禁用", "detail": "仅数据源框架"},
        {"name": "X / Twitter", "status": "已禁用", "detail": "仅数据源框架"},
        {"name": "Deep Sync", "status": "已禁用", "detail": "仅数据源框架"},
        {"name": "TradingView", "status": "已禁用", "detail": "仅交易实验室框架"},
        {"name": "技术面分析", "status": "手动", "detail": "TradingView 图表组件 + 点击后 DeepSeek"},
    ]
    env = [
        _env_status("X_API_BEARER_TOKEN", "X API"),
        _env_status("REDDIT_CLIENT_ID", "Reddit API"),
        _env_status("DEEP_SYNC_API_KEY", "Deep Sync API"),
        _env_status("DEEPSEEK_API_KEY", "DeepSeek"),
        _env_status("FINNHUB_API_KEY", "Finnhub"),
    ]
    return JSONResponse(content={
        "status": "ok",
        "process": {
            "pid": os.getpid(),
            "python": sys.version.split()[0],
            "uptime_seconds": uptime_seconds,
            "port": port,
            "branch": "codex/version-2.0",
        },
        "modules": modules,
        "providers": providers,
        "environment": env,
        "guardrails": [
            "不自动抓取 X / Reddit / 新闻",
            "没有手动触发就不运行 TradingAgents",
            "仪表盘框架不启动实时 K 线流",
            "外部数据源配置前保持禁用",
        ],
    })


@router.get("/radar", response_class=HTMLResponse, summary="Version 2.0 market radar shell")
async def radar_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("radar"))


@router.get("/sentiment", response_class=HTMLResponse, summary="Version 2.0 sentiment shell")
async def sentiment_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("sentiment"))


@router.get("/news-flow", response_class=HTMLResponse, summary="Version 2.0 news flow shell")
async def news_flow_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("news-flow"))


@router.get("/research-memo", response_class=HTMLResponse, summary="Version 2.0 research memo shell")
async def research_memo_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("research-memo"))


@router.get("/macro", response_class=HTMLResponse, summary="Version 2.0 macro shell")
async def macro_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("macro"))


@router.get("/trading-lab", response_class=HTMLResponse, summary="Version 2.0 trading lab shell")
async def trading_lab_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("trading-lab"))


@router.get("/technical-analysis", response_class=HTMLResponse, summary="Version 2.0 technical analysis")
async def technical_analysis_page(request: Request):
    return templates.TemplateResponse(request=request, name="technical_analysis.html", context={
        "title": "技术面分析",
    })


@router.get("/runtime", response_class=HTMLResponse, summary="Version 2.0 runtime status shell")
async def runtime_page(request: Request):
    return templates.TemplateResponse(request=request, name="v2_placeholder.html", context=_v2_context("runtime"))


@router.get("/watchlist", response_class=HTMLResponse, summary="自选股页面")
async def watchlist_page(request: Request):
    return templates.TemplateResponse(request=request, name="watchlist.html", context={
        "title": "自选股 - Watchlist",
    })


@router.get("/portfolio", response_class=HTMLResponse, summary="持仓管理页面")
async def portfolio_page(request: Request):
    return templates.TemplateResponse(request=request, name="portfolio.html", context={
        "title": "持仓管理 - Portfolio",
    })


@router.get("/settings", response_class=HTMLResponse, summary="设置页面")
async def settings_page(request: Request):
    config = get_config()
    available_models = config.get("available_models", {})
    models_flat = []
    for provider_models in available_models.values():
        if isinstance(provider_models, list):
            models_flat.extend(provider_models)
    personas = _persona_meta()
    per_agent = config.get("per_agent", {})
    default_model = config.get("defaults", {}).get("model", "")
    for p in personas:
        p["current_model"] = per_agent.get(p["id"], default_model)
    return templates.TemplateResponse(request=request, name="settings.html", context={
        "title": "设置",
        "personas": personas,
        "available_models": models_flat,
        "default_model": default_model,
    })


@router.get("/create-persona", response_class=HTMLResponse, summary="创建自定义投资人页面")
async def create_persona_page(request: Request):
    return templates.TemplateResponse(request=request, name="create_persona.html", context={
        "title": "创建自定义投资人",
    })


@router.get("/report/{ticker}", response_class=HTMLResponse, summary="深度分析报告全屏页面")
async def report_view_page(request: Request, ticker: str):
    """Dedicated full-page report view for a ticker. Auto-fetches report on load."""
    if not re.match(r'^[A-Za-z0-9.\-]{1,15}$', ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format.")
    return templates.TemplateResponse(request=request, name="report_view.html", context={
        "title": f"{ticker.upper()} Deep Analysis Report - Augur",
        "ticker": ticker.upper(),
    })
