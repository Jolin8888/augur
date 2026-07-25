"""HTML page routes: all browser-facing GET endpoints that render templates."""

import importlib.util
import os
import sys
import time
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from augur.config import get_config
from augur.workspace import get_workspace, resolve_landing_url
from dashboard.deps import _APP_START_TIME, get_registry, templates
from dashboard.routes.personas import _persona_meta

router = APIRouter()


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
        "title": "Market Radar",
        "heading": "Market Radar",
        "description": "SpikePanel-style market intelligence board for watchlists, factor signals, news heat, Reddit heat, X attention, and options flow.",
        "mode_label": "Framework shell",
        "guardrail": "This page is only the version 2.0 entry point. It does not fetch X, Reddit, Google News, TradingAgents, or real-time market data yet.",
        "cards": [
            {"title": "Signal Table", "body": "A dense radar table for tickers, scores, market move, source counts, and freshness.", "bullets": ["price and trend", "news count", "sentiment badge", "source receipts"], "wide": True},
            {"title": "Provider Status", "body": "Each data source will report idle, running, failed, or rate-limited.", "bullets": ["market", "news", "reddit", "x/twitter"]},
            {"title": "Manual Refresh", "body": "Refresh will stay user-controlled, with limits for tickers and source items.", "bullets": ["max tickers", "max headlines", "cooldown"]},
        ],
    },
    "sentiment": {
        "title": "Sentiment",
        "heading": "Market Sentiment",
        "description": "A controlled view of X, Reddit, and news tone without starting any crawler by default.",
        "mode_label": "Providers disabled",
        "guardrail": "Social and news providers will be opt-in. The page will show what is configured before any external request is made.",
        "cards": [
            {"title": "X / Twitter", "body": "Track selected KOLs, cashtags, and credible source posts when API access is configured.", "bullets": ["cashtag search", "KOL watchlist", "source links"]},
            {"title": "Reddit", "body": "Summarize subreddit activity, mentions, and top posts with rate-limit visibility.", "bullets": ["mentions", "top posts", "rate-limit status"]},
            {"title": "Sentiment Score", "body": "Keep sentiment separate from valuation and market factors so the dashboard does not become a black box.", "bullets": ["bull", "bear", "mixed", "no data"]},
        ],
    },
    "news-flow": {
        "title": "News Flow",
        "heading": "News Flow",
        "description": "Google News headlines and company/event news streams with source receipts.",
        "mode_label": "RSS not connected",
        "guardrail": "News refresh will be cached and limited. No background polling is active in this shell.",
        "cards": [
            {"title": "Google News", "body": "Ticker-focused headline feeds with source, timestamp, and linked receipt.", "bullets": ["ticker query", "sector query", "macro query"]},
            {"title": "Event Clusters", "body": "Group repeated headlines into one event so the page stays readable.", "bullets": ["earnings", "guidance", "regulatory", "product"]},
            {"title": "AI Summary", "body": "Summaries will cite source headlines and remain optional.", "bullets": ["facts first", "no advice", "traceable"]},
        ],
    },
    "research-memo": {
        "title": "Research Memo",
        "heading": "Research Memo",
        "description": "TradingAgents General+ dimensions compressed into a readable PM memo surface.",
        "mode_label": "Manual analysis only",
        "guardrail": "TradingAgents will not run automatically. It will require a manual button, ticker selection, and visible runtime status.",
        "cards": [
            {"title": "7 Analyst Dimensions", "body": "Market, Sentiment, News, Fundamentals, Macro, Flow, and Catalyst become memo sections.", "bullets": ["quality gate", "bull vs bear", "PM memo"], "wide": True},
            {"title": "Data Gaps", "body": "Missing Reddit, macro, or research data will lower confidence instead of pretending certainty.", "bullets": ["NO_DATA", "rate limited", "unconfigured"]},
            {"title": "Output", "body": "Final memo stays compact: bias, confidence, thesis, prove points, kill points, and monitoring items."},
        ],
    },
    "macro": {
        "title": "Macro",
        "heading": "Macro Monitor",
        "description": "Rates, inflation, commodities, dollar, central banks, and sector regime context.",
        "mode_label": "Snapshot shell",
        "guardrail": "Macro providers will refresh slowly by design and should never block the dashboard.",
        "cards": [
            {"title": "Regime Board", "body": "A compact board for rates, dollar, oil, yields, inflation, and risk appetite.", "bullets": ["daily cache", "event flags", "sector impact"]},
            {"title": "Ticker Impact", "body": "Map macro pressure to tickers and sectors without turning it into an opaque score.", "bullets": ["tailwind", "headwind", "neutral"]},
            {"title": "Provider Health", "body": "FRED or other macro failures will show clearly in Runtime Status."},
        ],
    },
    "trading-lab": {
        "title": "Trading Lab",
        "heading": "Trading Lab",
        "description": "TradingView, candle testing, Brooks-style price action labels, and drawing experiments.",
        "mode_label": "No live feed",
        "guardrail": "This page will load only when opened. It will not start a real-time market stream from the main dashboard.",
        "cards": [
            {"title": "TradingView", "body": "Embed when possible; otherwise open TradingView with the current ticker and timeframe.", "bullets": ["embed fallback", "open external", "no forced login"]},
            {"title": "Candle Layer", "body": "Prepare OHLCV and drawing interfaces before choosing a real-time data source.", "bullets": ["timeframe", "support/resistance", "trend lines"], "wide": True},
            {"title": "Brooks Action", "body": "Future labels for trend, range, breakout, pullback, wedge, and signal bars."},
        ],
    },
    "technical-analysis": {
        "title": "技术面分析",
        "heading": "技术面分析",
        "description": "TradingView 图表 + agent 式技术面研判报告，覆盖行情、均线、MACD、RSI、布林带、VWMA、支撑阻力、市场规则、SPY/QQQ 大盘背景和风险指数。",
        "mode_label": "TradingView chart",
        "guardrail": "页面打开时只加载 TradingView 图表。DeepSeek 研判必须手动触发，且需要 DEEPSEEK_API_KEY。",
        "cards": [
            {"title": "基础行情", "body": "收盘价、涨跌幅、阶段涨跌、5/20日均量、量比和量价背离提示。", "bullets": ["close", "change", "volume ratio"]},
            {"title": "技术指标", "body": "均线、MACD、RSI、布林带、VWMA 逐项拆解，保留多空信号和技术含义。", "bullets": ["EMA/SMA", "MACD", "RSI", "BOLL", "VWMA"], "wide": True},
            {"title": "大盘共振", "body": "SPY/QQQ 与主标的放在同一套趋势框架里判断，避免只看个股。", "bullets": ["SPY", "QQQ", "trend alignment"]},
        ],
    },
    "runtime": {
        "title": "Runtime Status",
        "heading": "Runtime Status",
        "description": "A visible control room for ports, providers, cache freshness, and task state.",
        "mode_label": "Local service visible",
        "guardrail": "This is where heavy work will become observable before it is allowed to run.",
        "cards": [
            {"title": "Local Server", "body": "Show the current dashboard port, process, uptime, and recent errors.", "bullets": ["port 8000", "uvicorn", "last health check"]},
            {"title": "Providers", "body": "Every external provider gets a visible state and error reason.", "bullets": ["disabled", "idle", "running", "failed", "rate limited"], "wide": True},
            {"title": "Controls", "body": "Future controls will stop tasks, clear caches, and set refresh limits."},
        ],
    },
}


V2_PAGE_STATE = {
    "radar": {
        "sources": [
            {"name": "Market snapshot", "status": "degraded", "mode": "REST fallback", "limit": "60s refresh"},
            {"name": "News heat", "status": "disabled", "mode": "manual", "limit": "50 headlines"},
            {"name": "Social heat", "status": "disabled", "mode": "manual", "limit": "25 posts"},
            {"name": "Options / flow", "status": "planned", "mode": "manual", "limit": "provider TBD"},
        ],
        "controls": ["Choose watchlist", "Refresh snapshot", "Open source receipts", "Export memo inputs"],
        "next_steps": ["Pick first tickers", "Confirm providers", "Set per-refresh limits"],
    },
    "sentiment": {
        "sources": [
            {"name": "X / Twitter KOLs", "status": "unconfigured", "mode": "manual", "limit": "API key required"},
            {"name": "Reddit posts", "status": "unconfigured", "mode": "manual", "limit": "API key required"},
            {"name": "Google News tone", "status": "disabled", "mode": "cache-first", "limit": "50 headlines"},
        ],
        "controls": ["Edit KOL list", "Edit subreddit list", "Run sentiment refresh", "Inspect raw receipts"],
        "next_steps": ["Confirm KOL handles", "Confirm subreddits", "Choose sentiment model"],
    },
    "news-flow": {
        "sources": [
            {"name": "Google News", "status": "disabled", "mode": "manual", "limit": "RSS/query limit"},
            {"name": "Company news", "status": "disabled", "mode": "manual", "limit": "per ticker"},
            {"name": "Macro headlines", "status": "disabled", "mode": "manual", "limit": "per topic"},
        ],
        "controls": ["Run headline pull", "Cluster duplicate headlines", "Pin important events"],
        "next_steps": ["Choose RSS/query path", "Set cache TTL", "Define event categories"],
    },
    "research-memo": {
        "sources": [
            {"name": "Market", "status": "degraded", "mode": "manual", "limit": "ticker scoped"},
            {"name": "Sentiment", "status": "disabled", "mode": "manual", "limit": "source scoped"},
            {"name": "News", "status": "disabled", "mode": "manual", "limit": "headline capped"},
            {"name": "Macro", "status": "disabled", "mode": "manual", "limit": "daily cache"},
            {"name": "TradingAgents General+", "status": "manual", "mode": "explicit run", "limit": "user confirmed"},
        ],
        "controls": ["Select ticker", "Run quality gate", "Generate PM memo", "Review bull/bear debate"],
        "next_steps": ["Wire memo schema", "Add confidence scoring", "Add kill-point checklist"],
    },
    "macro": {
        "sources": [
            {"name": "Rates", "status": "disabled", "mode": "daily cache", "limit": "slow refresh"},
            {"name": "Commodities", "status": "degraded", "mode": "REST fallback", "limit": "60s refresh"},
            {"name": "Dollar / FX", "status": "planned", "mode": "daily cache", "limit": "provider TBD"},
            {"name": "Central banks", "status": "planned", "mode": "manual", "limit": "event only"},
        ],
        "controls": ["Refresh regime board", "Map ticker impact", "Review macro risks"],
        "next_steps": ["Pick macro providers", "Set daily cache path", "Define sector mapping"],
    },
    "trading-lab": {
        "sources": [
            {"name": "TradingView", "status": "external", "mode": "open on demand", "limit": "no local stream"},
            {"name": "Candle test data", "status": "planned", "mode": "manual", "limit": "bounded OHLCV"},
            {"name": "Drawing layer", "status": "planned", "mode": "local only", "limit": "page scoped"},
            {"name": "Brooks labels", "status": "planned", "mode": "manual", "limit": "test mode"},
        ],
        "controls": ["Open TradingView", "Load candle sample", "Draw line", "Tag price action"],
        "next_steps": ["Choose chart library", "Confirm real-time source", "Define drawing persistence"],
    },
    "technical-analysis": {
        "sources": [
            {"name": "TradingView widget", "status": "external", "mode": "page load", "limit": "only this page"},
            {"name": "Indicator logic", "status": "ready", "mode": "local rules", "limit": "no API call"},
            {"name": "SPY / QQQ backdrop", "status": "planned", "mode": "TradingView chart", "limit": "manual refresh"},
            {"name": "DeepSeek report", "status": "unconfigured", "mode": "manual POST", "limit": "requires API key"},
        ],
        "controls": ["Load TradingView chart", "Open TradingView", "Run DeepSeek report", "Review support/resistance"],
        "next_steps": ["Connect TradingView MCP values", "Persist indicator snapshots", "Add broker/market rule profiles"],
    },
    "runtime": {
        "sources": [
            {"name": "Local process", "status": "running", "mode": "read-only", "limit": "local only"},
            {"name": "Provider registry", "status": "manual", "mode": "read-only", "limit": "no start"},
            {"name": "Cache health", "status": "planned", "mode": "read-only", "limit": "local files"},
        ],
        "controls": ["Refresh status", "Inspect provider config", "Stop future tasks", "Clear selected cache"],
        "next_steps": ["Add task registry", "Add cache inventory", "Add stop buttons"],
    },
}


class TechnicalDeepSeekBody(BaseModel):
    symbol: str = Field(default="NASDAQ:NVDA", max_length=40)
    timeframe: str = Field(default="D", max_length=8)
    market_profile: str = Field(default="US", max_length=20)
    metrics: dict = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)


def _v2_context(page_id: str) -> dict:
    page = V2_PAGES[page_id]
    state = V2_PAGE_STATE.get(page_id, {})
    return {"page_id": page_id, "state": state, **page}


def _v2_state_payload(page_id: str) -> dict:
    if page_id not in V2_PAGES:
        raise HTTPException(status_code=404, detail="Unknown version 2.0 page")
    return {
        "page_id": page_id,
        "title": V2_PAGES[page_id]["title"],
        "mode": V2_PAGES[page_id]["mode_label"],
        "guardrail": V2_PAGES[page_id]["guardrail"],
        **V2_PAGE_STATE.get(page_id, {}),
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
        "status": "configured" if configured else "unconfigured",
        "detail": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash") if configured else "set DEEPSEEK_API_KEY to enable",
    }


def _technical_prompt(body: TechnicalDeepSeekBody) -> str:
    return f"""请生成中文技术面分析报告，报告只作为研究参考，不构成投资建议。

标的：{body.symbol}
周期：{body.timeframe}
市场类型：{body.market_profile}
用户补充/已知指标：{body.metrics}
备注：{body.notes}

请严格按这些模块输出：
一、基础行情数据
二、技术指标详细分析
1. 均线系统：10EMA、20MA、50SMA、200SMA、均线排列、价格偏离、金叉/死叉
2. MACD：DIF、DEA、柱状图、金叉/死叉、动能扩大/收窄、背离
3. RSI：RSI(14)、50中轴、超买/超卖、强弱区间
4. 布林带：上轨、中轨、下轨、价格相对位置、趋势或超跌/超涨
5. VWMA：成交量加权均线、成交密集区、量价验证
三、关键支撑位与阻力位
四、市场规则/标的市场特性
五、SPY / QQQ 大盘背景
六、综合技术研判结论
七、操作观察条件
八、技术信号汇总表
九、风险指数

要求：
- 不要编造没有提供的精确价格或指标值；没有数据时写“待接入/暂无数据”。
- 可以给出判断框架、观察条件和风险等级，但不要给个性化买卖指令。
- 风格参考专业 agent 报告：结构化、表格化、直接指出多空证据和风险。"""


@router.get("/api/v2/technical/status", summary="Technical analysis provider status")
async def api_v2_technical_status():
    return JSONResponse(content={
        "status": "ok",
        "providers": [
            {"name": "TradingView widget", "status": "external", "detail": "loaded by browser only on /technical-analysis"},
            {"name": "TradingView MCP", "status": "manual", "detail": "available to Codex, not a dashboard background job"},
            _deepseek_status(),
        ],
        "models": {
            "default": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        },
        "guardrails": [
            "No DeepSeek request unless the user clicks Run",
            "No automatic TradingView MCP read from the dashboard",
            "No hidden background polling",
        ],
    })


@router.post("/api/v2/technical/deepseek-report", summary="Run manual DeepSeek technical report")
async def api_v2_technical_deepseek_report(body: TechnicalDeepSeekBody):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    if not api_key:
        return JSONResponse(content={
            "status": "unconfigured",
            "model": model,
            "message": "DEEPSEEK_API_KEY is not configured. The page is ready, but no AI request was sent.",
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
        return JSONResponse(content={"status": "ok", "model": model, "report": content, "usage": data.get("usage", {})})
    except Exception as exc:
        return JSONResponse(status_code=502, content={
            "status": "failed",
            "model": model,
            "message": f"DeepSeek request failed: {exc}",
        })


def _module_status(module_name: str, label: str, install_hint: str = "") -> dict:
    available = importlib.util.find_spec(module_name) is not None
    return {
        "name": label,
        "status": "available" if available else "missing",
        "detail": "installed" if available else (install_hint or f"{module_name} is not installed"),
    }


def _env_status(env_name: str, label: str) -> dict:
    configured = bool(os.environ.get(env_name))
    return {
        "name": label,
        "status": "configured" if configured else "unconfigured",
        "detail": env_name if configured else f"set {env_name} to enable",
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
        _module_status("websockets", "WebSocket transport", "install uvicorn[standard] or websockets"),
        _module_status("yfinance", "Market data / yfinance", "install augur-agents[data]"),
    ]
    providers = [
        {"name": "Dashboard", "status": "running", "detail": f"{request.url.scheme}://{request.url.hostname}:{port}"},
        {"name": "TradingAgents General+", "status": "manual", "detail": "not started from dashboard"},
        {"name": "Google News", "status": "disabled", "detail": "provider shell only"},
        {"name": "Reddit", "status": "disabled", "detail": "provider shell only"},
        {"name": "X / Twitter", "status": "disabled", "detail": "provider shell only"},
        {"name": "Deep Sync", "status": "disabled", "detail": "provider shell only"},
        {"name": "TradingView", "status": "disabled", "detail": "Trading Lab shell only"},
        {"name": "Technical Analysis", "status": "manual", "detail": "TradingView widget + DeepSeek on click"},
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
            "No automatic X/Reddit/News crawling",
            "No TradingAgents run without manual trigger",
            "No live candle stream from the dashboard shell",
            "External providers remain disabled until configured",
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
