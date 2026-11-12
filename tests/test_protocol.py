import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import market_cycle as m


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.now = datetime(2026, 11, 6, 10, tzinfo=timezone.utc)
        self.original_now = m.NOW
        m.NOW = self.now

    def tearDown(self):
        m.NOW = self.original_now
        self.temp.cleanup()

    def decision(self, **kw):
        d = dict(id="paper_test1", portfolio="stocks", action="BUY", symbol="AAPL",
                 amount_usd=100, model="GPT experimental", thesis="Test thesis",
                 decision_at_utc=self.now.isoformat(), sources=[])
        d.update(kw)
        return d

    def test_requires_safe_id_and_timestamp(self):
        with self.assertRaises(ValueError):
            m.validate_decision(self.folder / "paper_test1.json", self.decision(decision_at_utc="2020-01-01T00:00:00Z"))
        with self.assertRaises(ValueError):
            m.validate_decision(self.folder / "paper_test1.json", self.decision(symbol="AAPL/../../foo"))
        with self.assertRaises(ValueError):
            m.validate_decision(self.folder / "paper_test1.json", self.decision(id="different_id"))

    def test_crypto_restricts_unavailable_symbols(self):
        with self.assertRaises(ValueError):
            m.validate_decision(self.folder / "paper_test1.json", self.decision(portfolio="crypto", symbol="UNKNOWN"))

    def test_later_bar_only(self):
        accepted = self.now.isoformat()
        p = dict(startingCash=1000, cash=1000, positions={}, processed=["paper_test1"],
                 benchmark={"symbol": "SPY", "units": 0}, pending=[{
                     "id": "paper_test1", "portfolio": "stocks", "action": "BUY",
                     "symbol": "AAPL", "amount_usd": 100, "accepted_at": accepted,
                     "acceptedBarDate": "2026-11-05", "status": "pending"
                 }])
        st = {"portfolios": {"stocks": p, "crypto": {"cash": 1000, "positions": {}, "pending": []}}}
        bar = m.make_bar("2026-11-06", 100, 100, "test", "2026-11-06T09:00:00+00:00")
        market = {"prices": {"stocks": {"AAPL": bar}, "crypto": {}}}
        events = []
        m.execute_pending(st, market, events, set())
        self.assertEqual(len(p["pending"]), 1, "Never fill at an open before initial observation time")
        market["prices"]["stocks"]["AAPL"] = m.make_bar("2026-11-09", 110, 115, "test", "2026-11-09T14:30:00+00:00")
        m.execute_pending(st, market, events, set())
        self.assertEqual(len(p["pending"]), 0)
        self.assertEqual(events[0]["type"], "fill")
        self.assertLess(p["cash"], 1000)

    def test_newly_seen_order_cannot_fill_immediately(self):
        p = dict(cash=1000, positions={}, pending=[{"id":"decision1", "portfolio":"stocks", "action":"BUY", "symbol":"AAPL",
                                                    "amount_usd":100, "accepted_at":self.now.isoformat(), "acceptedBarDate":None}])
        market={"prices":{"stocks":{"AAPL":m.make_bar("2026-11-09",100,110,"test","2026-11-09T14:30:00+00:00")},"crypto":{}}}
        st={"portfolios":{"stocks":p,"crypto":{"cash":1000,"positions":{},"pending":[]}}}
        events=[]
        m.execute_pending(st,market,events,{"decision1"})
        self.assertFalse(events)
        self.assertEqual(len(p["pending"]),1)

    def test_position_cap(self):
        p = dict(cash=1000, positions={}, pending=[{"id":"decision2", "portfolio":"stocks", "action":"BUY", "symbol":"AAPL",
                                                    "amount_usd":500,"accepted_at":self.now.isoformat(),"acceptedBarDate":"2026-11-05"}])
        bar=m.make_bar("2026-11-09",100,100,"test","2026-11-09T14:30:00+00:00")
        st={"portfolios":{"stocks":p,"crypto":{"cash":1000,"positions":{},"pending":[]}}}
        ev=[]
        m.execute_pending(st,{"prices":{"stocks":{"AAPL":bar},"crypto":{}}},ev,set())
        self.assertEqual(ev[0]["type"],"rejection")
        self.assertEqual(p["cash"],1000)

    def test_buy_cap_uses_same_session_opening_marks(self):
        m.NOW += timedelta(days=4)
        p = dict(cash=600, positions={"SPY": 4}, pending=[{
            "id": "opening_cap", "portfolio": "stocks", "action": "BUY",
            "symbol": "AAPL", "amount_usd": 400, "accepted_at": self.now.isoformat(),
        }])
        state = {"portfolios": {"stocks": p}}
        prices = {"AAPL": m.make_bar("2026-11-09", 100, 100, "test", "2026-11-09T14:30:00Z")}
        market = {"prices": {"stocks": prices}}
        events = []

        prices["SPY"] = m.make_bar("2026-11-06", 100, 200, "test", "2026-11-06T14:30:00Z")
        m.execute_pending(state, market, events, set())
        self.assertEqual(len(p["pending"]), 1)
        self.assertEqual(events, [])

        prices["SPY"] = m.make_bar("2026-11-09", 100, 200, "test", "2026-11-09T14:30:00Z")
        m.execute_pending(state, market, events, set())
        self.assertEqual(events[0]["type"], "rejection")
        self.assertIn("35%", events[0]["reason"])
        self.assertEqual(p["cash"], 600)
        self.assertEqual(p["pending"], [])

    def test_unfilled_order_expires(self):
        p = dict(cash=1000, positions={}, pending=[{
            "id": "expired_buy", "portfolio": "stocks", "action": "BUY",
            "symbol": "AAPL", "amount_usd": 100,
            "accepted_at": (self.now - timedelta(days=7)).isoformat(),
        }])
        events = []
        m.execute_pending({"portfolios": {"stocks": p}}, {"prices": {}}, events, set())
        self.assertEqual(events[0]["type"], "rejection")
        self.assertIn("expired", events[0]["reason"])
        self.assertEqual(p["pending"], [])

    def test_agent_context_tracks_only_current_filled_position_episode(self):
        m.NOW = datetime(2026, 12, 1, 20, tzinfo=timezone.utc)

        def decision(identifier, day, action="BUY", portfolio="stocks"):
            return dict(id=identifier, type="decision", portfolio=portfolio, symbol="SPY",
                        action=action, decision_at_utc=f"2026-11-{day:02d}T15:00:00Z")

        def fill(identifier, day, action, quantity):
            return dict(type="fill", portfolio="stocks", symbol="SPY", decision_id=identifier,
                        bar_date=f"2026-11-{day:02d}", action=action, quantity=quantity)

        events = [
            decision("first_entry", 1), fill("first_entry", 2, "BUY", 10),
            decision("closed", 3, "SELL"), fill("closed", 3, "SELL", 10),
            decision("reopened", 4), fill("reopened", 4, "BUY", 8),
            decision("added", 9), fill("added", 9, "BUY", 3),
            decision("trimmed", 20, "SELL"), fill("trimmed", 20, "SELL", 2),
            decision("unfilled", 24),
            decision("other_account", 25, portfolio="crypto"),
        ]
        marks = [
            {"date": "2026-10-30", "equity": 1000, "benchmark": 1000},
            {"date": "2026-11-30", "equity": 1020, "benchmark": 1010},
            {"date": "2026-12-01", "equity": 1030, "benchmark": 1020},
        ]
        context = m.agent_context("stocks", {"positions": {"SPY": 9}}, marks, events)

        self.assertEqual(context["positions"]["SPY"]["opening_buy"]["id"], "reopened")
        self.assertEqual(context["positions"]["SPY"]["latest_filled_buy"]["id"], "added")
        self.assertEqual([d["id"] for d in context["recent_decisions"]], ["trimmed", "unfilled"])
        self.assertEqual(context["prior_month"]["decision_ids"][-1], "unfilled")
        self.assertEqual(len(context["prior_month"]["fills"]), 5)
        self.assertEqual(context["prior_month"]["start_mark"], marks[0])
        self.assertEqual(context["prior_month"]["end_mark"], marks[1])

    def test_bitcoin_trend_uses_complete_consecutive_daily_candles(self):
        start = self.now.replace(hour=0) - timedelta(days=30)
        candles = [
            [(start + timedelta(days=i)).timestamp(), 99, 999, 100, 100 + i]
            for i in range(31)
        ]
        with patch.object(m, "http_json", return_value=list(reversed(candles))):
            bar = m.crypto_bar("BTC")
        self.assertEqual(bar["close"], 129)
        self.assertEqual(bar["trend"]["sma_20"], 119.5)
        self.assertEqual(bar["trend"]["sma_20_five_days_earlier"], 114.5)
        self.assertAlmostEqual(bar["trend"]["return_5d"], 129 / 124 - 1)

        with patch.object(m, "http_json", return_value=candles[:15] + candles[16:]):
            self.assertNotIn("trend", m.crypto_bar("BTC"))

    def test_benchmark_initializes_at_first_observed_close(self):
        st={"portfolios":{"stocks":{"startingCash":1000,"cash":1000,"positions":{},"benchmark":{"symbol":"SPY","units":0}},
                          "crypto":{"startingCash":1000,"cash":1000,"positions":{},"benchmark":{"symbol":"BTC","units":0}}}}
        market={"prices":{"stocks":{"SPY":m.make_bar("2026-11-05",500,500,"test","2026-11-05T14:30:00+00:00")},
                          "crypto":{"BTC":m.make_bar("2026-11-05",90000,90000,"test","2026-11-05T00:00:00+00:00")}}}
        history={"portfolios":{"stocks":[],"crypto":[]}}
        m.mark_portfolios(st,market,history)
        self.assertEqual(history["portfolios"]["stocks"][0]["equity"],1000)
        self.assertEqual(history["portfolios"]["crypto"][0]["benchmark"],1000)


if __name__ == "__main__":
    unittest.main()
