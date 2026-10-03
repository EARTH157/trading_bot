import logging
import uvicorn

from config.settings import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("trading_bot")

def print_banner():
    banner = f"""
========================================================================
       🚀 AI MULTI-AGENT STOCK TRADING BOT & WEB DASHBOARD
========================================================================
  ● Mode:            {settings.APP_MODE.upper()} TRADING
  ● AI Model:        {settings.GEMINI_MODEL} {'(API Key Detected)' if settings.GEMINI_API_KEY else '(Heuristic Mode)'}
  ● Watchlist:       {', '.join(settings.watchlist_symbols)}
  ● Initial Balance: ${settings.INITIAL_BALANCE:,.2f} {settings.CURRENCY}
  ● Risk per trade:  {settings.MAX_RISK_PER_TRADE_PCT}% | Stop Loss: {settings.STOP_LOSS_PCT}% | Take Profit: {settings.TAKE_PROFIT_PCT}%
  ● Daily loss cap:  {settings.MAX_DAILY_LOSS_PCT}% | Risk check: every {settings.RISK_CHECK_INTERVAL_SECONDS}s | Auto pipeline: {f"every {settings.PIPELINE_INTERVAL_MINUTES}m" if settings.PIPELINE_INTERVAL_MINUTES > 0 else "manual"}
  ● Dashboard URL:   http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}
========================================================================
  4 Autonomous Agents Active:
    1. 🤖 News Scout (Scrapes news -> creates temp .md files)
    2. 🧠 Sentiment Analyst (Analyzes news sentiment via Gemini LLM)
    3. 📊 Market Screener (Evaluates EMA/RSI/Volume + Sentiment)
    4. 🛡️ Risk Guardian (Enforces position sizing, stop loss, order execution)
========================================================================
"""
    print(banner)

def main():
    print_banner()
    uvicorn.run(
        "dashboard.app:app",
        host=settings.DASHBOARD_HOST,
        port=settings.DASHBOARD_PORT,
        reload=settings.DASHBOARD_RELOAD,
        log_level="info"
    )

if __name__ == "__main__":
    main()
