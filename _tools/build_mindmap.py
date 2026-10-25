"""Baut mindmap.html aus daten.json und der Vorlage.
Aufruf: python build_mindmap.py firmen/BLK-BlackRock
(Claude macht das auf Zuruf; die HTML-Datei ist danach eigenständig und öffnet per Doppelklick.)
"""
import json, sys, pathlib

base = pathlib.Path(__file__).resolve().parent.parent
folder = base / sys.argv[1]
tpl = (base / '_tools' / 'mindmap_template.html').read_text(encoding='utf-8')
data = json.loads((folder / 'daten.json').read_text(encoding='utf-8'))
payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
assert '/*DATA*/null' in tpl
(folder / 'mindmap.html').write_text(tpl.replace('/*DATA*/null', payload), encoding='utf-8')
print('mindmap.html gebaut:', folder / 'mindmap.html')
