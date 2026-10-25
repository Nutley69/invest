#!/usr/bin/env python3
"""
Einfacher ereignisgesteuerter Backtester (Event-driven) für Aktien/ETFs.

Ablauf pro Kerze (Bar), immer nur ein Ereignis auf einmal:
    MarketEvent -> SignalEvent -> OrderEvent -> FillEvent

Schutz vor Look-ahead-Bias:
  * Die Strategie sieht nur Kerzen bis einschliesslich "heute" (Schlusskurs).
  * Ihre Order wird erst zur ERÖFFNUNG der NÄCHSTEN Kerze ausgeführt.
  * Stop-Loss wird gegen das Tief der Kerze geprüft (bei Gap: zum Eröffnungskurs).

Kosten sind eingebaut (Courtage, Stempelabgabe, Währungswechsel, Slippage),
Standardwerte entsprechen den Saxo-Angaben aus der Invest-Grundlage.

Aufruf (Beispiele):
    python backtest.py --ticker AAPL --start 2018-01-01
    python backtest.py --ticker NESN.SW --strategy trend --capital 750
    python backtest.py --csv meine_daten.csv --strategy sma
    python backtest.py --demo            # synthetische Daten, nur zum Testen

Benötigt: pandas, numpy, matplotlib   (Daten laden: yfinance, optional)
    pip install pandas numpy matplotlib yfinance

Keine Anlageberatung. Ein Backtest zeigt nur, was in der Vergangenheit
gewesen wäre, nicht was kommt.
"""
from __future__ import annotations

import argparse
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# 1. Ereignisse
# --------------------------------------------------------------------------
@dataclass
class MarketEvent:
    index: int
    date: pd.Timestamp


@dataclass
class SignalEvent:
    date: pd.Timestamp
    direction: str            # "LONG" (einsteigen) oder "EXIT" (aussteigen)
    stop_price: float | None = None   # geplanter Stop, nur bei LONG
    reason: str = ""


@dataclass
class OrderEvent:
    date: pd.Timestamp        # Datum, an dem die Order ausgelöst wurde
    side: str                 # "BUY" oder "SELL"
    quantity: int
    stop_price: float | None = None
    reason: str = ""


@dataclass
class FillEvent:
    date: pd.Timestamp
    side: str
    quantity: int
    price: float              # Ausführungskurs inkl. Slippage
    costs: float              # Courtage + Stempel + FX
    reason: str = ""


# --------------------------------------------------------------------------
# 2. Kostenmodell
# --------------------------------------------------------------------------
@dataclass
class CostModel:
    commission_rate: float = 0.0008   # 0,08 % (Saxo Classic)
    commission_min: float = 3.0       # Minimum pro Order
    stamp_duty: float = 0.0015        # 0,15 % auf ausländische Titel, Kauf UND Verkauf
    fx_rate: float = 0.0025           # 0,25 % Währungswechsel, Kauf UND Verkauf
    slippage: float = 0.0005          # 0,05 % schlechterer Kurs als Eröffnung (Spread/Markt)

    def costs(self, notional: float) -> float:
        commission = max(self.commission_min, self.commission_rate * notional)
        return commission + (self.stamp_duty + self.fx_rate) * notional


# --------------------------------------------------------------------------
# 3. Daten: gibt Kerzen eine nach der anderen heraus
# --------------------------------------------------------------------------
class DataHandler:
    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True)
        self.i = -1

    def __len__(self):
        return len(self.df)

    def next_bar(self) -> MarketEvent | None:
        if self.i + 1 >= len(self.df):
            return None
        self.i += 1
        return MarketEvent(self.i, self.df.loc[self.i, "Date"])

    def bar(self, i: int | None = None) -> pd.Series:
        return self.df.loc[self.i if i is None else i]

    def history(self) -> pd.DataFrame:
        """Nur Vergangenheit bis und mit heute, nie die Zukunft."""
        return self.df.iloc[: self.i + 1]


# --------------------------------------------------------------------------
# 4. Strategien (sehen nur history())
# --------------------------------------------------------------------------
class Strategy:
    name = "basis"
    _prev_in = False
    _blocked = False

    def on_market(self, data: DataHandler, in_position: bool) -> SignalEvent | None:
        raise NotImplementedError

    def decide(self, good: bool, in_position: bool) -> str | None:
        """
        good = Bedingung für "im Markt sein". Gibt "LONG", "EXIT" oder None zurück.
        Wurde die Position durch den Stop-Loss geschlossen, obwohl die Bedingung noch gilt,
        wird erst wieder eingestiegen, nachdem die Bedingung einmal weggefallen ist
        (sonst kauft man sofort wieder zurück und zahlt die Kosten doppelt).
        """
        if self._prev_in and not in_position and good:
            self._blocked = True
        if not good:
            self._blocked = False
        self._prev_in = in_position
        if good and not in_position and not self._blocked:
            return "LONG"
        if not good and in_position:
            return "EXIT"
        return None


class SmaCross(Strategy):
    """Kauft, wenn die schnelle Durchschnittslinie über die langsame steigt, sonst raus."""

    def __init__(self, fast=20, slow=50, stop_pct=0.05):
        self.fast, self.slow, self.stop_pct = fast, slow, stop_pct
        self.name = f"SMA-Kreuzung {fast}/{slow}"

    def on_market(self, data, in_position):
        h = data.history()
        if len(h) < self.slow + 1:
            return None
        close = h["Close"]
        fast, slow = close.rolling(self.fast).mean(), close.rolling(self.slow).mean()
        up = fast.iloc[-1] > slow.iloc[-1]
        act = self.decide(up, in_position)
        if act == "LONG":
            return SignalEvent(h["Date"].iloc[-1], "LONG",
                               stop_price=close.iloc[-1] * (1 - self.stop_pct),
                               reason=f"SMA{self.fast} über SMA{self.slow}")
        if act == "EXIT":
            return SignalEvent(h["Date"].iloc[-1], "EXIT", reason="SMA-Kreuzung nach unten")
        return None


class TrendRegime(Strategy):
    """
    Regime-Filter (Idee aus dem Video): nur handeln, wenn der Markt im Aufwärtstrend
    UND die Schwankung nicht extrem ist.
      Trend:   Kurs über der 100-Tage-Linie und die Linie steigt.
      Ruhe:    20-Tage-Volatilität unter einer Obergrenze (annualisiert).
    Einfaches Regelwerk statt K-Means, dafür ohne Zukunftsdaten und leicht zu prüfen.
    """

    def __init__(self, trend_len=100, vol_len=20, max_vol=0.35, stop_pct=0.05):
        self.trend_len, self.vol_len, self.max_vol, self.stop_pct = trend_len, vol_len, max_vol, stop_pct
        self.name = f"Trend-Regime (SMA{trend_len}, Vol<{int(max_vol*100)}%)"

    def on_market(self, data, in_position):
        h = data.history()
        if len(h) < self.trend_len + 6:
            return None
        close = h["Close"]
        sma = close.rolling(self.trend_len).mean()
        vol = close.pct_change().rolling(self.vol_len).std().iloc[-1] * math.sqrt(252)
        good = close.iloc[-1] > sma.iloc[-1] and sma.iloc[-1] > sma.iloc[-6] and vol < self.max_vol
        act = self.decide(bool(good), in_position)
        if act == "LONG":
            return SignalEvent(h["Date"].iloc[-1], "LONG",
                               stop_price=close.iloc[-1] * (1 - self.stop_pct),
                               reason=f"Trend ok, Vol {vol:.0%}")
        if act == "EXIT":
            return SignalEvent(h["Date"].iloc[-1], "EXIT", reason=f"Regime vorbei, Vol {vol:.0%}")
        return None


class BuyHold(Strategy):
    name = "Buy & Hold"

    def on_market(self, data, in_position):
        if not in_position and data.i == 0:
            return SignalEvent(data.bar()["Date"], "LONG", reason="Start")
        return None


STRATEGIES = {"sma": SmaCross, "trend": TrendRegime}


# --------------------------------------------------------------------------
# 5. Portfolio: macht aus Signalen Orders (Positionsgrösse nach Risikoregel)
# --------------------------------------------------------------------------
class Portfolio:
    def __init__(self, capital: float, risk_per_trade: float | None, max_position_pct: float = 1.0):
        self.cash = capital
        self.start_capital = capital
        self.risk_per_trade = risk_per_trade      # Franken, die pro Trade höchstens riskiert werden
        self.max_position_pct = max_position_pct
        self.shares = 0
        self.stop_price: float | None = None
        self.entry_price = 0.0
        self.entry_date = None
        self.entry_costs = 0.0
        self.equity_curve: list[tuple] = []
        self.trades: list[dict] = []
        self.total_costs = 0.0

    @property
    def in_position(self) -> bool:
        return self.shares > 0

    def on_signal(self, sig: SignalEvent, last_close: float) -> OrderEvent | None:
        if sig.direction == "EXIT" and self.in_position:
            return OrderEvent(sig.date, "SELL", self.shares, reason=sig.reason)
        if sig.direction == "LONG" and not self.in_position:
            equity = self.cash
            qty_cap = int(equity * self.max_position_pct / (last_close * 1.03))   # 3 % Puffer für Kosten und Eröffnungs-Gap
            if self.risk_per_trade and sig.stop_price:
                risk_per_share = last_close - sig.stop_price
                qty_risk = int(self.risk_per_trade / risk_per_share) if risk_per_share > 0 else qty_cap
                qty = min(qty_cap, qty_risk)
            else:
                qty = qty_cap
            if qty >= 1:
                return OrderEvent(sig.date, "BUY", qty, stop_price=sig.stop_price, reason=sig.reason)
        return None

    def on_fill(self, f: FillEvent, stop_price: float | None):
        gross = f.price * f.quantity
        self.total_costs += f.costs
        if f.side == "BUY":
            self.cash -= gross + f.costs
            self.shares += f.quantity
            self.stop_price = stop_price
            self.entry_price, self.entry_date, self.entry_costs = f.price, f.date, f.costs
        else:
            self.cash += gross - f.costs
            pnl = (f.price - self.entry_price) * f.quantity - self.entry_costs - f.costs
            self.trades.append({
                "Einstieg": self.entry_date.date(), "Ausstieg": f.date.date(),
                "Stück": f.quantity, "Kurs_ein": round(self.entry_price, 2),
                "Kurs_aus": round(f.price, 2), "Kosten": round(self.entry_costs + f.costs, 2),
                "Gewinn_Verlust": round(pnl, 2), "Grund_aus": f.reason,
            })
            self.shares, self.stop_price = 0, None

    def mark(self, date, close: float):
        self.equity_curve.append((date, self.cash + self.shares * close))


# --------------------------------------------------------------------------
# 6. Broker-Simulation: führt Orders zur nächsten Eröffnung aus, prüft Stops
# --------------------------------------------------------------------------
class SimBroker:
    def __init__(self, costs: CostModel):
        self.costs = costs
        self.pending: list[OrderEvent] = []

    def submit(self, order: OrderEvent):
        self.pending.append(order)

    def _fill(self, date, side, qty, base_price, reason) -> FillEvent:
        slip = self.costs.slippage
        price = base_price * (1 + slip) if side == "BUY" else base_price * (1 - slip)
        return FillEvent(date, side, qty, price, self.costs.costs(price * qty), reason)

    def execute_pending(self, bar: pd.Series) -> list[tuple[FillEvent, float | None]]:
        fills = []
        for o in self.pending:
            fills.append((self._fill(bar["Date"], o.side, o.quantity, bar["Open"], o.reason), o.stop_price))
        self.pending.clear()
        return fills

    def check_stop(self, bar: pd.Series, portfolio: Portfolio) -> FillEvent | None:
        if portfolio.in_position and portfolio.stop_price and bar["Low"] <= portfolio.stop_price:
            base = min(bar["Open"], portfolio.stop_price)       # Gap nach unten: schlechterer Kurs
            return self._fill(bar["Date"], "SELL", portfolio.shares, base, "Stop-Loss")
        return None


# --------------------------------------------------------------------------
# 7. Die Ereignis-Schleife
# --------------------------------------------------------------------------
def run_backtest(df, strategy, capital=750.0, risk_per_trade=30.0, costs=None, max_position_pct=1.0):
    costs = costs or CostModel()
    data = DataHandler(df)
    pf = Portfolio(capital, risk_per_trade, max_position_pct)
    broker = SimBroker(costs)
    queue: deque = deque()

    while (m := data.next_bar()) is not None:
        queue.append(m)
        while queue:
            ev = queue.popleft()
            if isinstance(ev, MarketEvent):
                bar = data.bar()
                # 1) Gestern ausgelöste Orders zur heutigen Eröffnung ausführen
                for fill, stop in broker.execute_pending(bar):
                    queue.append((fill, stop))
                # 2) danach Stop-Loss während der heutigen Kerze prüfen
                queue.append(("STOPCHECK", bar))
                # 3) zuletzt sieht die Strategie den heutigen Schluss
                queue.append(("STRATEGIE", bar))
            elif isinstance(ev, tuple) and ev[0] == "STOPCHECK":
                stop_fill = broker.check_stop(ev[1], pf)
                if stop_fill:
                    queue.appendleft((stop_fill, None))
            elif isinstance(ev, tuple) and isinstance(ev[0], FillEvent):
                pf.on_fill(ev[0], ev[1])
            elif isinstance(ev, tuple) and ev[0] == "STRATEGIE":
                bar = ev[1]
                sig = strategy.on_market(data, pf.in_position or bool(broker.pending))
                if sig:
                    queue.append(sig)
                pf.mark(bar["Date"], bar["Close"])
            elif isinstance(ev, SignalEvent):
                order = pf.on_signal(ev, data.bar()["Close"])
                if order:
                    queue.append(order)
            elif isinstance(ev, OrderEvent):
                broker.submit(ev)

    # Offene Position am Ende zum letzten Schluss bewerten (Kosten für Verkauf abziehen)
    if pf.in_position:
        last = data.bar()
        fill = broker._fill(last["Date"], "SELL", pf.shares, last["Close"], "Backtest-Ende")
        pf.on_fill(fill, None)
        pf.equity_curve[-1] = (last["Date"], pf.cash)
    return pf


# --------------------------------------------------------------------------
# 8. Kennzahlen
# --------------------------------------------------------------------------
def metrics(pf: Portfolio, label: str) -> dict:
    eq = pd.Series({d: v for d, v in pf.equity_curve})
    rets = eq.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total = eq.iloc[-1] / pf.start_capital - 1
    cagr = (eq.iloc[-1] / pf.start_capital) ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = rets.mean() / rets.std() * math.sqrt(252) if rets.std() > 0 else 0.0
    t = pd.DataFrame(pf.trades)
    wins = (t["Gewinn_Verlust"] > 0).sum() if len(t) else 0
    return {
        "Strategie": label,
        "Endkapital": round(eq.iloc[-1], 2),
        "Gesamtrendite": f"{total:+.1%}",
        "Rendite p.a.": f"{cagr:+.1%}",
        "Max. Verlust (Drawdown)": f"{dd:.1%}",
        "Sharpe": round(sharpe, 2),
        "Trades": len(t),
        "Trefferquote": f"{wins / len(t):.0%}" if len(t) else "-",
        "Kosten total": round(pf.total_costs, 2),
    }


# --------------------------------------------------------------------------
# 9. Daten laden
# --------------------------------------------------------------------------
def load_yf(ticker, start, end):
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise SystemExit(f"Keine Daten für {ticker}. Ticker prüfen (Schweiz: NESN.SW, Deutschland: SAP.DE).")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.reset_index()[["Date", "Open", "High", "Low", "Close"]].dropna()


def load_csv(path):
    df = pd.read_csv(path, parse_dates=["Date"])
    return df[["Date", "Open", "High", "Low", "Close"]].dropna().sort_values("Date")


def demo_data(n=1500, seed=7):
    """Künstliche Kurse mit wechselnden Phasen (ruhig, Trend, Krise). Nur zum Testen."""
    rng = np.random.default_rng(seed)
    regimes = [(0.0002, 0.008), (0.0010, 0.010), (-0.0030, 0.030), (0.0008, 0.012)]
    rets, i = [], 0
    while len(rets) < n:
        mu, sd = regimes[i % len(regimes)]
        length = int(rng.integers(120, 300))
        rets += list(rng.normal(mu, sd, length))
        i += 1
    close = 100 * np.exp(np.cumsum(rets[:n]))
    opn = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    spread = np.abs(rng.normal(0, 0.006, n))
    high = np.maximum(opn, close) * (1 + spread)
    low = np.minimum(opn, close) * (1 - spread)
    dates = pd.bdate_range("2019-01-01", periods=n)
    return pd.DataFrame({"Date": dates, "Open": opn, "High": high, "Low": low, "Close": close})


# --------------------------------------------------------------------------
# 10. Hauptprogramm
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Event-driven Backtester")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ticker", help="Yahoo-Ticker, z.B. AAPL, NESN.SW, SAP.DE")
    src.add_argument("--csv", help="CSV mit Spalten Date,Open,High,Low,Close")
    src.add_argument("--demo", action="store_true", help="synthetische Testdaten")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--strategy", choices=STRATEGIES, default="trend")
    ap.add_argument("--capital", type=float, default=750.0, help="Kapital des Kurzfrist-Topfs (CHF)")
    ap.add_argument("--risk", type=float, default=30.0, help="max. Verlust pro Trade (CHF), 0 = aus")
    ap.add_argument("--stop", type=float, default=0.05, help="Stop-Loss in Prozent vom Einstieg, z.B. 0.05")
    ap.add_argument("--no-costs", action="store_true", help="Kosten abschalten (nur zum Vergleich)")
    ap.add_argument("--out", default="backtest_ergebnis", help="Ausgabeordner")
    a = ap.parse_args()

    df = demo_data() if a.demo else load_csv(a.csv) if a.csv else load_yf(a.ticker, a.start, a.end)
    label = "DEMO" if a.demo else (a.ticker or Path(a.csv).stem)

    costs = CostModel(0, 0, 0, 0, 0) if a.no_costs else CostModel()
    strat = STRATEGIES[a.strategy](stop_pct=a.stop)
    pf = run_backtest(df, strat, a.capital, a.risk or None, costs)
    bh = run_backtest(df, BuyHold(), a.capital, None, costs)

    table = pd.DataFrame([metrics(pf, strat.name), metrics(bh, "Buy & Hold")]).set_index("Strategie")
    print(f"\n=== {label}  {df['Date'].iloc[0].date()} bis {df['Date'].iloc[-1].date()}  "
          f"Kapital {a.capital:.0f} ===\n")
    print(table.T.to_string(), "\n")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    trades = pd.DataFrame(pf.trades)
    trades.to_csv(out / f"{label}_trades.csv", index=False, sep=";")
    table.to_csv(out / f"{label}_kennzahlen.csv", sep=";")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for p, name, c in [(pf, strat.name, "#1f4fd8"), (bh, "Buy & Hold", "#888888")]:
        s = pd.Series({d: v for d, v in p.equity_curve})
        ax1.plot(s.index, s.values, label=name, color=c, lw=1.6)
        ax2.fill_between(s.index, (s / s.cummax() - 1) * 100, 0, color=c, alpha=0.25)
    ax1.set_title(f"{label}: Kapitalverlauf nach Kosten")
    ax1.set_ylabel("Kapital (CHF)"); ax1.legend(); ax1.grid(alpha=0.3)
    ax2.set_ylabel("Verlust vom Hoch (%)"); ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / f"{label}_chart.png", dpi=130)
    print(f"Gespeichert in: {out.resolve()}")
    if len(pf.trades) < 30:
        print("\nHinweis: weniger als 30 Trades, das Ergebnis ist statistisch nicht belastbar.")


if __name__ == "__main__":
    main()
