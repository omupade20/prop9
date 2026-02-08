# core/market_streamer.py

import json
import datetime
import upstox_client
from config.settings import ACCESS_TOKEN

from strategy.scanner import MarketScanner
from strategy.vwap_filter import VWAPCalculator
from strategy.strategy_engine import StrategyEngine

from execution.execution_engine import ExecutionEngine
from execution.order_executor import OrderExecutor
from execution.trade_monitor import TradeMonitor
from execution.risk_manager import RiskManager
from execution.trade_logger import TradeLogger


FEED_MODE = "full"

# ---------------- LOAD UNIVERSE ----------------
with open("data/nifty500_keys.json", "r") as f:
    INSTRUMENT_LIST = json.load(f)

# ---------------- CORE OBJECTS ----------------
scanner = MarketScanner(max_len=600)   # keep ~600 5m bars
vwap_calculators = {inst: VWAPCalculator() for inst in INSTRUMENT_LIST}

strategy_engine = StrategyEngine(scanner, vwap_calculators)

order_executor = OrderExecutor()
trade_monitor = TradeMonitor()
risk_manager = RiskManager()
trade_logger = TradeLogger()

execution_engine = ExecutionEngine(
    order_executor,
    trade_monitor,
    risk_manager,
    trade_logger
)

signals_today = {}


# ---------------- STREAMER ----------------
def start_market_streamer():
    global signals_today

    config = upstox_client.Configuration()
    config.access_token = ACCESS_TOKEN
    api_client = upstox_client.ApiClient(config)

    # Initialize V3 Websocket streamer
    streamer = upstox_client.MarketDataStreamerV3(
        api_client,
        INSTRUMENT_LIST,
        FEED_MODE
    )

    def on_message(message):
        """
        Called for each WebSocket update.
        message is a dict from the Upstox V3 feed.
        """

        now = datetime.datetime.now()
        today = now.date().isoformat()

        if today not in signals_today:
            signals_today[today] = set()

        # Parse feed ticks
        feeds = message.get("feeds", {})

        current_prices = {}

        for inst_key, feed_info in feeds.items():

            # Latest Trading Price Container
            data = feed_info.get("fullFeed", {}).get("marketFF", {})

            # Parse LTP safely
            try:
                ltp = float(data["ltpc"]["ltp"])
            except Exception:
                continue

            # Keep current LTP for exit logic
            current_prices[inst_key] = ltp

            # OHLC information if present (assumed to be a complete 5m bar)
            ohlc = data.get("marketOHLC", {}).get("ohlc", [])

            # If this instrument has 5m OHLC data, process it
            if ohlc:
                # Use the last provided completed bar
                last_ohlc = ohlc[-1]
                try:
                    open_p = float(last_ohlc.get("open", ltp))
                    high = float(last_ohlc["high"])
                    low = float(last_ohlc["low"])
                    close = float(last_ohlc["close"])
                    volume = float(last_ohlc.get("volume", 0))
                    ts = last_ohlc.get("ts")  # timestamp from feed, if available
                except Exception:
                    # Skip if bar fields invalid
                    continue

                # ---- UPDATE SCANNER WITH 5m BAR ----
                # Use timestamp from feed if present; otherwise fallback to current time
                time_iso = ts if ts else now.strftime("%Y-%m-%dT%H:%M:%S")

                scanner.append_ohlc_bar(
                    inst_key,
                    time_iso,
                    open_p,
                    high,
                    low,
                    close,
                    volume
                )

                # ---- STRATEGY EVALUATION ON NEW 5m BAR ----
                decision = strategy_engine.evaluate(inst_key, ltp)

                if decision and decision.state.startswith("EXECUTE"):
                    # Prevent duplicate signals for same instrument on same day
                    if inst_key not in signals_today[today]:
                        signals_today[today].add(inst_key)
                        execution_engine.handle_entry(inst_key, decision, ltp)

        # ---- EXIT HANDLING (runs on each message) ----
        execution_engine.handle_exits(current_prices, now)

    # Register callback for messages
    streamer.on("message", on_message)

    # Connect to data feed
    streamer.connect()

    print("🚀 Elite intraday trading system started (5m base, MTF 15m/30m)")

