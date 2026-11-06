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
