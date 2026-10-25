# Backtesting (Papier-Phase)

Prüft eine Handelsregel an historischen Kursen, bevor echtes Geld im Spiel ist.
Ereignisgesteuert: Preis -> Signal -> Order -> Ausführung, immer eine Kerze nach der anderen.
Keine Anlageberatung.

## Einmalige Einrichtung (Windows)

1. Python 3.11 oder neuer installieren (python.org, Haken bei "Add to PATH").
2. In der Eingabeaufforderung: `pip install pandas numpy matplotlib yfinance`

## Benutzen

Im Ordner `_tools/backtest` ausführen:

    python backtest.py --demo                              # Test mit künstlichen Daten
    python backtest.py --ticker AAPL --start 2018-01-01
    python backtest.py --ticker NESN.SW --strategy sma
    python backtest.py --ticker AAPL --capital 750 --risk 30 --stop 0.05

Ticker: US einfach `AAPL`, Schweiz `.SW` (NESN.SW), Deutschland `.DE` (SAP.DE).
Eigene Daten: `--csv datei.csv` mit den Spalten Date,Open,High,Low,Close.

Ergebnis im Ordner `backtest_ergebnis/`: Chart (PNG), Kennzahlen und alle Trades als CSV
(Trades lassen sich ins `_journal/papier-journal.csv` übernehmen).

## Strategien

- `trend` (Standard): nur im Aufwärtstrend (Kurs über SMA100, Linie steigt) und bei nicht extremer Schwankung.
- `sma`: schnelle (20) gegen langsame (50) Durchschnittslinie.
- Immer verglichen mit Buy & Hold.

## Eingebaute Regeln und Annahmen

- Order wird zur Eröffnung der NÄCHSTEN Kerze ausgeführt (kein Blick in die Zukunft).
- Stop-Loss wird gegen das Tief geprüft; bei Gap nach unten gilt der schlechtere Kurs.
- Positionsgrösse: höchstens `--risk` CHF Verlust bis zum Stop (Standard 30 CHF, deine 1-%-Regel),
  begrenzt durch das Kapital. Die Kosten kommen zum Verlust noch dazu.
- Nach einem Stop-Out steigt die Strategie erst wieder ein, wenn ihre Bedingung einmal weggefallen ist.
- Kosten (Saxo-Werte, Stand Grundlage): Courtage 0,08 % (min. 3), Stempel 0,15 %, Währung 0,25 %,
  Slippage 0,05 %, jeweils bei Kauf und Verkauf. In `CostModel` oben im Skript anpassbar.
  `--no-costs` zeigt zum Vergleich das Ergebnis ohne Kosten.
- Vereinfachung: Alles wird in einer Währung gerechnet, Dividenden sind in den Kursen enthalten (angepasste Kurse).

## Grenzen (wichtig)

- Tageskerzen: für Trades über Minuten bis Stunden reicht das nicht. Dafür braucht es Intraday-Daten.
- Unter 30 Trades ist ein Ergebnis Zufall. Mehrere Titel und Zeiträume testen.
- Nicht an einem Titel die Parameter so lange drehen, bis es gut aussieht (Überanpassung).
  Besser: Parameter auf einem Zeitraum wählen, auf einem anderen prüfen.
- Vergangenheit ist keine Garantie.
