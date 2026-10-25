# Invest-Grundlage (Projekt «infofeed»)

Ziel: Geld verdienen, mit mehreren Standbeinen (langfristig, kurzfristig). Dies ist die Arbeitsgrundlage. Keine Anlageberatung.

## Ordnerstruktur

```
invest/
  index.html                 START HIER: eine Datei, die alles zeigt (Doppelklick)
  README.md                  diese Datei: Regeln und Befehle
  watchlist.csv              Firmen, die ich beobachte (mit Triggern und Terminen)
  _vorlagen/dossier-vorlage.md   Gerüst für jeden Firmenbericht
  _journal/papier-journal.csv    Übungshandel auf Papier (und später echte Trades)
  _tools/                    Mindmap-Vorlage und Bau-Skript
  firmen/<TICKER-Name>/
    bericht.md               schriftlicher Bericht
    daten.json               alle Fakten, Verbindungen, Quellen (Quelle der Wahrheit)
    mindmap.html             interaktive Mindmap (Doppelklick, öffnet im Browser)
    stand.txt                Datum der letzten Erneuerung
```

## Befehle an Claude

- «Neue Firma: <Name>»: Recherche, bericht.md, daten.json, mindmap.html, Eintrag in watchlist.csv.
  Jede neue Firma wird automatisch mit den bestehenden verbunden: gemeinsame Aktionäre, Lieferanten oder Kunden (Feld `entity`) und Firmen mit eigenem Dossier (Feld `dossier`) erscheinen im Gesamtnetz und als «Auch in den Dossiers» in den Knoten.
- «Erneuere <Firma>»: nur Neues einarbeiten, Stand-Datum aktualisieren, Mindmap neu bauen.
- «Was steht an?»: Termine aller Firmen in der Watchlist (Berichte, Dividenden) prüfen.
- «Auswertung <Firma> Bericht»: neue Zahlen gegen die Erwartung (Konsens) einordnen.
- «Seite neu bauen»: baut `index.html` aus allen Dossiers neu (passiert nach jeder Änderung automatisch).
- Erneuert wird nur auf Zuruf.

## Startseite

Die Datei `index.html` ist eigenständig und braucht kein Internet. Sie enthält Übersicht, alle Berichte, alle Mindmaps, die chronologischen Berichtstermine (Quartals- und Jahresberichte aller Firmen, vergangene mit Ergebnis), das Gesamtnetz, diese Regeln und das Trade-Journal. Im Journal legt «Speichern» die Datei `_journal/papier-journal.csv` im gewählten Ordner ab (nur Chrome und Edge; sonst Download). Die einzelnen Dateien in den Firmenordnern bleiben zusätzlich bestehen (zum Beispiel `mindmap.html` einzeln öffnen).

## Verlässlichkeit jeder Aussage

| Stufe | Bedeutung | Mindmap-Linie |
|---|---|---|
| belegt | Primärquelle (Firma, SEC, Börse) | durchgezogen |
| berichtet | Medien oder Datenseiten, nicht selbst gegengeprüft | gestrichelt |
| vermutet | Einordnung oder Annahme ohne Quelle | gepunktet |

Jede Verbindung hat Quelle und Datum. Was ich nicht finde, steht als Lücke im Bericht, nicht als Behauptung.

## Wichtige Fallen bei Zahlen

- **GAAP gegen «as adjusted»:** Der Markt vergleicht meist den bereinigten Gewinn je Aktie mit dem Konsens. Ein Vergleich von GAAP mit Konsens zeigt fälschlich einen «Miss».
- **Gut/schlecht ist relativ:** Der Kurs reagiert auf Abweichung von der Erwartung und auf den Ausblick, nicht auf die Zahl selbst.
- **Datenseiten widersprechen sich** (Kurs, 52-Wochen-Hoch, Reaktion am Berichtstag). Ich nenne dann beide Werte.

## Risikoregeln (aus deinen Vorgaben)

- Startkapital rund 3000 CHF, aufgeteilt in ETF, Aktien, Kurzfrist-Topf.
- Maximal tragbarer Verlust: 300 CHF gesamt.
- Pro Trade riskierst du höchstens 30 CHF (1 % des Kapitals), mit Stop-Loss vor dem Einstieg.
- Monatsverlust 150 CHF: Pause bis zum nächsten Monat.
- Gesamtverlust 300 CHF: Stopp und Ansatz überdenken.
- Kurzfrist-Topf klein halten (zum Beispiel 600 bis 900 CHF).

## Papier-Phase für Kurzfrist-Trades

1. Mindestens 2 bis 3 Monate und mindestens 30 Trades auf Papier, jeder mit Begründung im Journal.
2. Alle Kosten einrechnen: Courtage, Stempelabgabe (Saxo: 0,15 % auf ausländische Titel, bei Kauf und Verkauf), Währungswechsel (Saxo: 0,25 %), Spread.
3. Erst wenn das Ergebnis nach Kosten klar positiv ist (und nicht von einem einzigen Glückstreffer abhängt), kleine echte Beträge.
4. Gewinne aus sehr aktivem Handel können in der Schweiz steuerlich als selbständige Erwerbstätigkeit gelten. Früh mit einer Steuerberatung klären.

## Broker (Stand Oktober 2026, Vergleichsblogs, bitte selbst prüfen)

- Langfristig: Saxo (Classic: 0,08 %, min. 3 CHF bzw. 1 USD; keine Depotgebühr; kostenloser Steuerauszug).
- Kurzfristig: Interactive Brokers ist deutlich günstiger (keine Stempelabgabe, Währungswechsel fast gratis), aber komplexer und mit kostenpflichtigem Steuerauszug.
