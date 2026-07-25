"""HTML page routes: all browser-facing GET endpoints that render templates."""

import importlib.util
import os
import sys
import time
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

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
    ]
    env = [
        _env_status("X_API_BEARER_TOKEN", "X API"),
        _env_status("REDDIT_CLIENT_ID", "Reddit API"),
        _env_status("DEEP_SYNC_API_KEY", "Deep Sync API"),
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
