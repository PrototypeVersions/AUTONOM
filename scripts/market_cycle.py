#!/usr/bin/env python3
"""AUTONOM forward-only paper-market cycle. Python stdlib only.

This is NOT an AI agent. It fetches public reference bars, admits prospectively
committed decision files, and simulates fills only on later eligible bars.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INBOX = ROOT / "decisions" / "inbox"
NOW = datetime.now(timezone.utc)
STOCK_BASE = (
    "SPY", "QQQ", "IWM", "RSP", "XLE", "XLV", "SGOV",
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "TSLA",
)
CRYPTO_BASE = ("BTC", "ETH", "SOL", "ADA", "LINK")
CRYPTO_ALLOWED = set(CRYPTO_BASE) | {"AVAX", "DOGE", "LTC", "BCH"}
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,7}$")
FEE_RATE = 0.001
SLIPPAGE = 0.0005
MAX_POSITION_FRACTION = 0.35
ORDER_LIFETIME = timedelta(days=7)
MAX_POSITIONS = {"stocks": 10, "crypto": 6}
NEW_YORK = ZoneInfo("America/New_York")
CENTRAL = ZoneInfo("America/Chicago")
HEADERS = {"User-Agent": "AUTONOM-Research/1.0 (+https://github.com/PrototypeVersions/AUTONOM)", "Accept": "application/json,text/csv,application/xml,*/*"}


def read_json(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write_json(name, obj):
    p = DATA / name
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + ".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(p)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def http_json(url):
    return json.loads(fetch(url))


def as_utc(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timezone is required")
    return d.astimezone(timezone.utc)


def stock_bar(symbol):
    # Stooq CSV: includes OHLC for completed sessions. Fallback to Yahoo chart.
    today = NOW.date()
    begin = (today - timedelta(days=16)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    url = "https://stooq.com/q/d/l/?s=" + urllib.parse.quote(symbol.lower() + ".us") + "&i=d&d1=" + begin + "&d2=" + end
    try:
        rows = list(csv.DictReader(io.StringIO(fetch(url))))
        parsed = [r for r in rows if r.get("Date") and r.get("Open") and r.get("Close")]
        parsed = [r for r in parsed if valid_completed_stock_day(r["Date"])]
        if parsed:
            r = max(parsed, key=lambda x: x["Date"])
            return make_bar(r["Date"], float(r["Open"]), float(r["Close"]), "Stooq EOD", market_open_utc(r["Date"]).isoformat())
    except Exception as exc:
        print(f"stooq {symbol}: {exc}", file=sys.stderr)
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol) + "?range=15d&interval=1d"
    j = http_json(url)["chart"]["result"][0]
    quote = j["indicators"]["quote"][0]
    bars = []
    for i, ts in enumerate(j.get("timestamp", [])):
        d = datetime.fromtimestamp(ts, timezone.utc).astimezone(NEW_YORK).date().isoformat()
        op, cl = quote["open"][i], quote["close"][i]
        if op is not None and cl is not None and valid_completed_stock_day(d):
            bars.append(make_bar(d, op, cl, "Yahoo daily chart", market_open_utc(d).isoformat()))
    if not bars:
        raise ValueError(f"No completed daily bar for {symbol}")
    return max(bars, key=lambda x: x["date"])


def market_open_utc(day):
    return datetime.combine(date.fromisoformat(day), time(9, 30), NEW_YORK).astimezone(timezone.utc)


def valid_completed_stock_day(day):
    d = date.fromisoformat(day)
    if d.weekday() >= 5:
        return False
    # Bar from today is eligible only when regular NYSE session has completed.
    close = datetime.combine(d, time(16, 15), NEW_YORK).astimezone(timezone.utc)
    return NOW >= close


def make_bar(day, op, cl, source, bar_start):
    if not 0 < float(op) < 1e8 or not 0 < float(cl) < 1e8:
        raise ValueError("Invalid price")
    return {"date": day, "open": round(float(op), 8), "close": round(float(cl), 8), "source": source, "bar_start_utc": bar_start}


def crypto_bar(symbol):
    # Coinbase public market candles. Never use the currently unfinished UTC day.
    end = datetime.combine(NOW.date(), time(0), timezone.utc)
    start = end - timedelta(days=30 if symbol == "BTC" else 8)
    query = urllib.parse.urlencode({"granularity": 86400, "start": start.isoformat(), "end": end.isoformat()})
    url = "https://api.exchange.coinbase.com/products/" + symbol + "-USD/candles?" + query
    candles = http_json(url)
    if not isinstance(candles, list):
        raise ValueError("No Coinbase bars")
    bars = []
    for item in candles:
        if not isinstance(item, list) or len(item) < 5:
            continue
        dt = datetime.fromtimestamp(item[0], timezone.utc)
        if dt + timedelta(days=1) > NOW or dt >= end:
            continue
        bars.append(make_bar(dt.date().isoformat(), item[3], item[4], "Coinbase Exchange daily candle", dt.isoformat()))
    if not bars:
        raise ValueError("No completed Coinbase candle")
    bars_by_date = {bar["date"]: bar for bar in bars}
    latest = bars_by_date[max(bars_by_date)]
    if symbol == "BTC":
        last_day = date.fromisoformat(latest["date"])
        days = [(last_day - timedelta(days=offset)).isoformat() for offset in range(24, -1, -1)]
        if all(day in bars_by_date for day in days):
            closes = [bars_by_date[day]["close"] for day in days]
            latest["trend"] = {
                "sma_20": round(sum(closes[-20:]) / 20, 8),
                "sma_20_five_days_earlier": round(sum(closes[:20]) / 20, 8),
                "return_5d": round(closes[-1] / closes[-6] - 1, 8),
            }
    return latest


def symbols_for(which, state):
    base = STOCK_BASE if which == "stocks" else CRYPTO_BASE
    p = state["portfolios"][which]
    extra = list(p["positions"]) + [d["symbol"] for d in p["pending"] if d.get("symbol")]
    return sorted(set(base) | {s for s in extra if isinstance(s, str) and SYMBOL_PATTERN.fullmatch(s)})


def update_prices(market, state, errors):
    for which in ("stocks", "crypto"):
        for sym in symbols_for(which, state):
            try:
                fresh = stock_bar(sym) if which == "stocks" else crypto_bar(sym)
                current = market["prices"].setdefault(which, {}).get(sym)
                if not current or fresh["date"] >= current["date"]:
                    market["prices"][which][sym] = fresh
            except Exception as exc:
                errors.append(f"{which}/{sym}: {str(exc)[:150]}")
    market["as_of"] = NOW.isoformat()


def read_news(research, errors):
    queries = {"stocks": "US stock market economy earnings", "crypto": "bitcoin ethereum cryptocurrency market"}
    for which, q in queries.items():
        try:
            url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
            doc = ET.fromstring(fetch(url, timeout=15))
            items = []
            for node in doc.findall("./channel/item")[:8]:
                title = html.unescape("".join(node.findtext("title", "")).strip())
                link = node.findtext("link", "").strip()
                if title and link.startswith("https://"):
                    items.append({"title": title[:300], "url": link, "published": node.findtext("pubDate")})
            research["items"][which] = items
        except Exception as exc:
            errors.append(f"news/{which}: {str(exc)[:150]}")
    research["as_of"] = NOW.isoformat()


def validate_decision(path, raw):
    if not isinstance(raw, dict):
        raise ValueError("Decision must be an object")
    identifier = str(raw.get("id", ""))
    if not re.fullmatch(r"[a-zA-Z0-9_-]{5,80}", identifier) or identifier != path.stem:
        raise ValueError("ID must match safe filename stem")
    which = raw.get("portfolio")
    if which not in ("stocks", "crypto"):
        raise ValueError("portfolio must be stocks or crypto")
    action = str(raw.get("action", "")).upper()
    if action not in ("BUY", "SELL", "HOLD"):
        raise ValueError("action must be BUY, SELL or HOLD")
    symbol = str(raw.get("symbol", "")).upper()
    if action != "HOLD" and not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Invalid ticker symbol")
    if which == "crypto" and action != "HOLD" and symbol not in CRYPTO_ALLOWED:
        raise ValueError("Crypto symbol not in supported spot universe")
    if action == "HOLD":
        symbol = ""
    amount = raw.get("amount_usd", 0)
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or (action != "HOLD" and not 10 <= amount <= 1000):
        raise ValueError("amount_usd must be $10–$1,000 for buy/sell")
    if action == "HOLD":
        amount = 0
    model = str(raw.get("model", ""))[:120].strip()
    thesis = str(raw.get("thesis", ""))[:2400].strip()
    if not model or not thesis:
        raise ValueError("model and thesis are required")
    issued = as_utc(str(raw.get("decision_at_utc", "")))
    if issued > NOW + timedelta(minutes=5) or issued < NOW - timedelta(days=10):
        raise ValueError("Decision timestamp too far in the future or stale")
    links = raw.get("sources", [])
    if not isinstance(links, list):
        raise ValueError("sources must be an array")
    links = [str(x)[:800] for x in links[:6] if isinstance(x, str) and x.startswith(("https://", "http://"))]
    return {"id": identifier, "portfolio": which, "action": action, "symbol": symbol, "amount_usd": float(amount),
            "decision_at_utc": issued.isoformat(), "model": model, "thesis": thesis, "sources": links,
            "risk_notes": str(raw.get("risk_notes", ""))[:1000]}


def ingest_decisions(state, market, events, errors):
    new_ids = set()
    for path in sorted(INBOX.glob("*.json")):
        # IDs are global across both portfolios, not just within each one.
        if any(path.stem in state["portfolios"][k]["processed"] for k in ("stocks", "crypto")):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            d = validate_decision(path, raw)
            which = d["portfolio"]
            p = state["portfolios"][which]
            p["processed"].append(d["id"])
            e = {"type": "decision", "at": NOW.isoformat(), **d, "title": d["action"] + (" " + d["symbol"] if d["symbol"] else " / no trade"),
                 "note": "First observed by AUTONOM engine; model identity comes from submitted metadata and is not cryptographically verified."}
            events.append(e)
            if d["action"] != "HOLD":
                seen_bar = market["prices"].get(which, {}).get(d["symbol"], {})
                p["pending"].append({**d, "accepted_at": NOW.isoformat(), "acceptedBarDate": seen_bar.get("date"), "status": "pending"})
                new_ids.add(d["id"])
        except Exception as exc:
            # A malformed decision must not cause repeated error events. Track its file stem.
            for k in ("stocks", "crypto"):
                state["portfolios"][k]["processed"].append(path.stem)
            msg = f"Rejected {path.name}: {str(exc)[:200]}"
            errors.append(msg)
            events.append({"type": "rejection", "at": NOW.isoformat(), "id": path.stem, "title": "Rejected decision file", "reason": msg, "portfolio": "system"})
    return new_ids


def equity(which, p, market, *, bar_date, price_field):
    total = float(p["cash"])
    for symbol, qty in p["positions"].items():
        bar = market["prices"].get(which, {}).get(symbol)
        if not bar or bar["date"] != bar_date:
            return None
        total += float(qty) * bar[price_field]
    return total


def reject(events, d, reason):
    events.append({"type": "rejection", "at": NOW.isoformat(), "id": d["id"] + "-rejected", "portfolio": d["portfolio"],
                   "title": d["action"] + " " + d["symbol"] + " rejected", "reason": reason, "model": "AUTONOM engine"})


def execute_pending(state, market, events, new_ids):
    for which, p in state["portfolios"].items():
        retained = []
        for order in p["pending"]:
            if order["id"] in new_ids:
                retained.append(order)
                continue
            accepted_at = as_utc(order["accepted_at"])
            if NOW - accepted_at >= ORDER_LIFETIME:
                reject(events, order, "Order expired after seven days without an eligible fill.")
                continue
            bar = market["prices"].get(which, {}).get(order["symbol"])
            if not bar or not bar.get("bar_start_utc"):
                retained.append(order)
                continue
            # The bar must START after the server first observed the decision, and
            # must be newer than the previous recorded bar. No hindsight fills.
            if as_utc(bar["bar_start_utc"]) <= accepted_at:
                retained.append(order)
                continue
            if order.get("acceptedBarDate") and bar["date"] <= order["acceptedBarDate"]:
                retained.append(order)
                continue
            action, sym, amount = order["action"], order["symbol"], order["amount_usd"]
            open_price = bar["open"]
            fill_price = open_price * (1 + SLIPPAGE if action == "BUY" else 1 - SLIPPAGE)
            qty = amount / fill_price
            fee = amount * FEE_RATE
            err = None
            held = float(p["positions"].get(sym, 0))
            if action == "BUY":
                opening_equity = equity(which, p, market, bar_date=bar["date"], price_field="open")
                if opening_equity is None:
                    retained.append(order)
                    continue
                if p["cash"] + 1e-6 < amount + fee:
                    err = "Insufficient cash including estimated transaction fee."
                elif (held * open_price + amount) > MAX_POSITION_FRACTION * opening_equity + 1e-6:
                    err = "Per-symbol position limit of 35% of current portfolio equity exceeded."
                elif not held and len([x for x in p["positions"].values() if x > 0]) >= MAX_POSITIONS[which]:
                    err = "Maximum simultaneous positions exceeded."
                if not err:
                    p["cash"] -= amount + fee
                    p["positions"][sym] = held + qty
            elif action == "SELL":
                if held + 1e-8 < qty:
                    err = "Insufficient units to sell at the later eligible open reference price."
                if not err:
                    p["cash"] += amount - fee
                    rest = held - qty
                    if rest < 1e-8:
                        p["positions"].pop(sym, None)
                    else:
                        p["positions"][sym] = rest
            if err:
                reject(events, order, err)
                continue
            events.append({"type": "fill", "at": NOW.isoformat(), "id": order["id"] + "-fill", "decision_id": order["id"],
                           "portfolio": which, "action": action, "symbol": sym, "quantity": round(qty, 10),
                           "price": round(fill_price, 8), "reference_open": open_price, "fee": round(fee, 6),
                           "bar_date": bar["date"], "model": "AUTONOM engine",
                           "title": f"{action} {sym} paper fill", "note": "Filled at next eligible daily open reference price with modeled slippage and fee; not an executable broker fill."})
        p["pending"] = retained


def mark_portfolios(state, market, history):
    for which, p in state["portfolios"].items():
        sym = p["benchmark"]["symbol"]
        b = market["prices"].get(which, {}).get(sym)
        if not b:
            continue
        if not p["benchmark"]["units"]:
            p["benchmark"]["units"] = p["startingCash"] / b["close"]
            p["benchmark"]["baseline_date"] = b["date"]
            p["benchmark"]["baseline_price"] = b["close"]
        total = equity(which, p, market, bar_date=b["date"], price_field="close")
        if total is None:
            continue
        bench = p["benchmark"]["units"] * b["close"]
        rows = history["portfolios"].setdefault(which, [])
        # One canonical observation per benchmark date, no synthetic backfill.
        observation = {"date": b["date"], "equity": round(total, 6), "benchmark": round(bench, 6),
                       "cash": round(float(p["cash"]), 6)}
        if not rows or b["date"] > rows[-1]["date"]:
            rows.append(observation)
        elif rows[-1]["date"] == b["date"]:
            # Intraday refresh can update marks, not invent additional days.
            rows[-1] = observation


def decision_date(decision):
    return as_utc(decision["decision_at_utc"]).astimezone(CENTRAL).date()


def position_context(positions, fills, decisions_by_id):
    context = {}
    for symbol, quantity in positions.items():
        remaining = float(quantity)
        latest = opening = None
        for fill in reversed(fills):
            if fill["symbol"] != symbol:
                continue
            if fill["action"] == "SELL":
                remaining += fill["quantity"]
                continue
            decision = decisions_by_id.get(fill["decision_id"])
            if latest is None:
                latest = decision
            remaining -= fill["quantity"]
            if remaining <= 1e-8:
                opening = decision
                break
        context[symbol] = {
            "opening_buy": opening,
            "latest_filled_buy": latest if latest != opening else None,
        }
    return context


def prior_month_review(decisions, fills, marks, today):
    month_start = today.replace(day=1)
    prior_start = (month_start - timedelta(days=1)).replace(day=1)
    start, end = prior_start.isoformat(), month_start.isoformat()
    month_decisions = [
        event["id"] for event in decisions if prior_start <= decision_date(event) < month_start
    ]
    month_fills = [event for event in fills if start <= event["bar_date"] < end]
    month_marks = [row for row in marks if start <= row["date"] < end]
    if not month_decisions and not month_fills and not month_marks:
        return None

    preceding = next((row for row in reversed(marks) if row["date"] < start), None)
    cash_fractions = [row["cash"] / row["equity"] for row in month_marks if "cash" in row and row["equity"] > 0]
    return {
        "month": start[:7],
        "decision_ids": month_decisions,
        "fills": month_fills,
        "start_mark": preceding or (month_marks[0] if month_marks else None),
        "end_mark": month_marks[-1] if month_marks else None,
        "valuations": len(month_marks),
        "mean_cash_fraction": round(sum(cash_fractions) / len(cash_fractions), 6) if cash_fractions else None,
    }


def agent_context(which, account, marks, events):
    today = NOW.astimezone(CENTRAL).date()
    decisions = [event for event in events if event["portfolio"] == which and event["type"] == "decision"]
    fills = [event for event in events if event["portfolio"] == which and event["type"] == "fill"]
    cutoff = today - timedelta(days=13)
    recent = [event for event in decisions if cutoff <= decision_date(event) <= today]
    return {
        "as_of": NOW.isoformat(),
        "recent_decisions": recent[-14:],
        "positions": position_context(account["positions"], fills, {event["id"]: event for event in decisions}),
        "prior_month": prior_month_review(decisions, fills, marks, today),
    }


def main():
    state = read_json("state.json", {})
    market = read_json("market.json", {"prices": {"stocks": {}, "crypto": {}}})
    history = read_json("history.json", {"portfolios": {"stocks": [], "crypto": []}})
    research = read_json("research.json", {"items": {"stocks": [], "crypto": []}})
    events = read_json("events.json", [])
    status = read_json("status.json", {"market": {}, "agent": {"connected": False}})
    errors = []
    # First-seen time is always server/runtime time, not an untrusted model assertion.
    new_ids = ingest_decisions(state, market, events, errors)
    update_prices(market, state, errors)
    read_news(research, errors)
    # Market data may be available but a full session behind; mark that honestly.
    local = NOW.astimezone(NEW_YORK)
    expected = local.date() if local.time() >= time(16, 15) else local.date() - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    spy_date = market["prices"].get("stocks", {}).get("SPY", {}).get("date")
    btc_date = market["prices"].get("crypto", {}).get("BTC", {}).get("date")
    if spy_date and spy_date < expected.isoformat():
        errors.append(f"Stock reference quote delayed: SPY {spy_date}, expected session {expected.isoformat()}; possible exchange holiday/provider lag.")
    expected_crypto = (NOW.date() - timedelta(days=1)).isoformat()
    if btc_date and btc_date < expected_crypto:
        errors.append(f"Crypto reference quote delayed: BTC {btc_date}, expected completed UTC day {expected_crypto}.")
    execute_pending(state, market, events, new_ids)
    mark_portfolios(state, market, history)
    success = all(market["prices"].get(w, {}).get(s) for w, s in (("stocks", "SPY"), ("crypto", "BTC")))
    st = status.setdefault("market", {})
    st["status"] = "ok" if success and not errors else "degraded" if success else "unavailable"
    st["last_attempt_at"] = NOW.isoformat()
    if success and not errors:
        st["last_success_at"] = NOW.isoformat()
    st["errors"] = errors[:15]
    decisions = [event for event in events if event["type"] == "decision"]
    latest_by_portfolio = {event["portfolio"]: event["at"] for event in decisions}
    status["agent"] = {
        "connected": False,
        "label": (
            "Scheduled decision files recorded; the engine does not authenticate model identity."
            if decisions else "Awaiting the first accepted decision file."
        ),
        "decision_files_seen": len(decisions),
        "last_decision_at": latest_by_portfolio,
    }
    for name, obj in [("state.json", state), ("market.json", market), ("history.json", history),
                      ("research.json", research), ("events.json", events), ("status.json", status)]:
        write_json(name, obj)
    for which, account in state["portfolios"].items():
        marks = history["portfolios"].get(which, [])
        write_json(f"agent-{which}.json", agent_context(which, account, marks, events))
    print(json.dumps({"status": st["status"], "prices": {k: len(v) for k, v in market["prices"].items()},
                      "events": len(events), "errors": errors[:8]}, indent=2))


if __name__ == "__main__":
    main()
