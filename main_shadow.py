"""
main_shadow.py — True Shadow Mode Pipeline

Integrates:
- REAL NSE Market Data (via Kite WebSocket, if authenticated)
- REAL Features
- REAL ML Model
- REAL Stock Ranking
- REAL Portfolio Construction
- REAL Risk Checks
- SIMULATED Orders (Strictly NO Real Broker Orders)

Live trading remains firmly disabled (`LiveTradingDisabledError` architecture is enforced).
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

# Ensure project root is in path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data.realtime.kite_feed import KiteRealTimeFeedAdapter
from data.realtime import get_global_health_monitor
from features.pipeline import FeaturePipeline
from ml.equity.inference import MLInferenceEngine
from ranking.models import DefaultRankingEngine
from portfolio.construction import PortfolioConstructor
from risk.engine import RiskEngine
from execution.paper import get_global_paper_orchestrator

from data.realtime import get_global_quote_cache

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ShadowMode")

# The unified universe
SHADOW_UNIVERSE = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

def run_shadow_mode_cycle(feed: KiteRealTimeFeedAdapter):
    """Execute a single deterministic shadow mode tick using real feed data."""
    logger.info("--- SHADOW MODE CYCLE START ---")
    
    if not feed.is_connected():
        logger.error("DATA_SOURCE=KITE_LIVE | FEED_STATE=DISCONNECTED | ACTION=ABORTING_CYCLE")
        return
        
    quotes = feed.get_snapshot()
    if not quotes:
        logger.warning("No market data snapshot available from Kite yet. Skipping cycle.")
        return

    # Log explicit source
    last_tick_time = max([q.timestamp for q in quotes.values()]) if quotes else None
    logger.info(f"DATA_SOURCE=KITE_LIVE | FEED_STATE=CONNECTED | SYMBOLS_SUBSCRIBED={len(feed.get_subscribed_symbols())}")
    logger.info(f"LAST_TICK_TIMESTAMP={last_tick_time.isoformat() if last_tick_time else 'N/A'}")
    logger.info(f"Received {len(quotes)} real-time quotes.")

    try:
        engine = MLInferenceEngine()
        logger.info(f"ML Model: Loaded active production model.")
    except Exception as e:
        logger.warning(f"ML Model unavailable: {e}")

    orchestrator = get_global_paper_orchestrator()
    
    try:
        cycle = orchestrator.run_cycle(
            universe=SHADOW_UNIVERSE,
            force_market_open=True,  # Bypass time-of-day checks for pure testing
            disable_synthetic_fallback=True, # STRICT SHADOW MODE
        )
        if cycle:
            logger.info(f"Shadow Cycle {cycle.cycle_id} complete. State: {cycle.state.value}")
            if cycle.error_message:
                logger.error(f"Cycle Error: {cycle.error_message}")
            logger.info(f"Signals generated: {len(cycle.signals)}")
            logger.info(f"Portfolio decisions: {len(cycle.decisions)}")
            
            # Simulated Orders
            account = orchestrator.broker.get_account()
            logger.info(f"Simulated Equity: {account.total_equity}")
            logger.info(f"Simulated Cash: {account.cash}")
            logger.info(f"Simulated Positions: {len(orchestrator.broker.get_positions())}")
            
    except Exception as e:
        logger.error(f"Shadow Orchestrator Failed: {e}")
        
    logger.info("--- SHADOW MODE CYCLE COMPLETE ---")


def main():
    logger.info("Starting APEX-QUANT Shadow Mode Pipeline...")
    logger.info("CRITICAL ALIGNMENT: REAL MARKET DATA -> SIMULATED EXECUTION.")

    feed = KiteRealTimeFeedAdapter()
    if not feed.connect():
        logger.error("Failed to connect to Kite feed. Shadow mode requires REAL data.")
        logger.error("Check KITE_API_KEY and KITE_ACCESS_TOKEN. Exiting.")
        sys.exit(1)
        
    global_cache = get_global_quote_cache()
    feed.register_callback(global_cache.update)
    feed.subscribe(SHADOW_UNIVERSE)

    try:
        while True:
            run_shadow_mode_cycle(feed)
            time.sleep(60) # Run every minute
    except KeyboardInterrupt:
        logger.info("Shadow Mode Terminated gracefully.")
        feed.disconnect()

if __name__ == "__main__":
    main()

