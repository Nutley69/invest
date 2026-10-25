"""Baut index.html (die eine Startdatei) aus allen Dossiers.
Aufruf: python _tools/build_site.py
Liest: firmen/*/daten.json, bericht.md, README.md, watchlist.csv. Baut zuerst alle Mindmaps neu.
(Claude macht das auf Zuruf; index.html ist danach eigenständig und öffnet per Doppelklick.)
"""
import csv, json, pathlib, re, datetime
import markdown

base = pathlib.Path(__file__).resolve().parent.parent
tpl_mm = (base / '_tools' / 'mindmap_template.html').read_text(encoding='utf-8')
tpl_site = (base / '_tools' / 'site_template.html').read_text(encoding='utf-8')


def md_html(text):
    md = markdown.Markdown(extensions=['tables', 'toc', 'sane_lists'])
    h = md.convert(text)
    return re.sub(r'<a href="(https?://[^"]+)"', r'<a target="_blank" rel="noopener" href="\1"', h)


# 1. Alle Daten laden
daten = []
for d in sorted((base / 'firmen').iterdir()):
    if (d / 'daten.json').exists():
        daten.append((d, json.loads((d / 'daten.json').read_text(encoding='utf-8'))))


def zentrum(data):
    return next(n for n in data['knoten'] if n['kat'] == 'firma')['id']


def tick_von_dossier(n):
    return n.get('dossier')


# 2. Gemeinsame Akteure (Feld "entity") und Verweise (Feld "dossier") dossieruebergreifend finden
ent = {}   # entity -> [(ticker, node)]
for d, data in daten:
    t = data['firma']['ticker']
    for n in data['knoten']:
        if n.get('entity'):
            ent.setdefault(n['entity'], []).append((t, n))
for d, data in daten:
    t = data['firma']['ticker']
    for n in data['knoten']:
        e = n.get('entity')
        auch = sorted({x for x, _ in ent.get(e, []) if x != t}) if e else []
        if n.get('dossier') and n['dossier'] != t:
            auch = sorted(set(auch) | {n['dossier']})
        if auch:
            n['auch'] = auch

# 3. Gesamtnetz bauen
VERL_RANG = {'belegt': 0, 'berichtet': 1, 'vermutet': 2}
netz_n, netz_e, seen = [], [], set()
tickers = [data['firma']['ticker'] for _, data in daten]
for d, data in daten:
    f = data['firma']
    netz_n.append({'id': 'F:' + f['ticker'], 'name': f['name'].replace(', Inc.', '').replace(' Inc.', '') + ' (' + f['ticker'] + ')', 'kat': 'firma', 'w': 6,
                   'text': f"Eigenes Dossier mit Bericht und Mindmap. Stand {f['stand']}.", 'betrag': '', 'datum': f['stand'], 'verl': 'belegt',
                   'quellen': [], 'dossier': f['ticker']})


def kante_zum_zentrum(data, nid):
    c = zentrum(data)
    for e in data['kanten']:
        if {e['von'], e['zu']} == {c, nid}:
            return e
    return None


for e_key, lst in sorted(ent.items()):
    if len({x for x, _ in lst}) < 2:
        continue
    kats = {n['kat'] for _, n in lst}
    node = {'id': 'E:' + e_key, 'name': lst[0][1]['name'], 'kat': 'doppelt' if 'doppelt' in kats else lst[0][1]['kat'],
            'w': max(n['w'] for _, n in lst),
            'text': ' '.join(f"[{x}] {n['text']}" for x, n in lst),
            'betrag': ' | '.join(f"{x}: {n['betrag']}" for x, n in lst if n['betrag']), 'datum': '',
            'verl': max((n['verl'] for _, n in lst), key=lambda v: VERL_RANG[v]),
            'quellen': [], 'auch': sorted({x for x, _ in lst})}
    seen_u = set()
    for x, n in lst:
        for q in n['quellen']:
            if q['url'] not in seen_u:
                seen_u.add(q['url']); node['quellen'].append(q)
    netz_n.append(node)
    for x, n in lst:
        dd = next(dt for _, dt in daten if dt['firma']['ticker'] == x)
        k = kante_zum_zentrum(dd, n['id'])
        netz_e.append({'von': 'E:' + e_key, 'zu': 'F:' + x, 'label': (x + ': ' + k['label']) if k else x, 'verl': k['verl'] if k else n['verl'],
                       'betrag': k['betrag'] if k else n['betrag'], 'quellen': k['quellen'] if k else n['quellen']})

for d, data in daten:                      # Verweise zwischen Firmen
    f = data['firma']
    for n in data['knoten']:
        o = n.get('dossier')
        if o and o in tickers and o != f['ticker']:
            pair = tuple(sorted((f['ticker'], o)))
            if pair in seen:
                continue
            seen.add(pair)
            k = kante_zum_zentrum(data, n['id'])
            netz_e.append({'von': 'F:' + f['ticker'], 'zu': 'F:' + o,
                           'label': f"{n['name']}: " + (k['label'] if k else 'Verbindung'), 'verl': n['verl'], 'betrag': n['betrag'], 'quellen': n['quellen']})

netz_data = {'netz': True, 'firma': {'name': 'Gesamtnetz', 'ticker': 'NETZ', 'boerse': 'alle Dossiers', 'stand': datetime.date.today().strftime('%d.%m.%Y'),
             'kennzahlen': [{'k': 'Dossiers', 'v': str(len(daten))}, {'k': 'Gemeinsame Akteure', 'v': str(sum(1 for n in netz_n if n['id'].startswith('E:')))},
                            {'k': 'Direkte Firmenverbindungen', 'v': str(len(seen))}], 'termine': []},
             'knoten': netz_n, 'kanten': netz_e}
netz_html = tpl_mm.replace('/*DATA*/null', json.dumps(netz_data, ensure_ascii=False).replace('</', '<\\/'))

# 4. Einzelne Dossiers schreiben
firmen = []
for d, data in daten:
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    mm = tpl_mm.replace('/*DATA*/null', payload)
    (d / 'mindmap.html').write_text(mm, encoding='utf-8')
    f = data['firma']
    firmen.append({
        'ticker': f['ticker'], 'name': f['name'], 'boerse': f['boerse'], 'typ': f.get('typ', ''),
        'stand': f['stand'], 'ordner': d.name, 'kennzahlen': f['kennzahlen'], 'termine': f['termine'],
        'bericht_html': md_html((d / 'bericht.md').read_text(encoding='utf-8')),
        'mindmap_html': mm,
    })

with open(base / 'watchlist.csv', encoding='utf-8-sig', newline='') as fh:
    watch = list(csv.DictReader(fh, delimiter=';'))

site = {
    'firmen': firmen,
    'netz_html': netz_html,
    'netz_info': {'akteure': [n['name'] for n in netz_n if n['id'].startswith('E:')], 'verbindungen': [e['label'] for e in netz_e if e['von'].startswith('F:') and e['zu'].startswith('F:')]},
    'regeln_html': md_html((base / 'README.md').read_text(encoding='utf-8')),
    'watchlist': watch,
    'gebaut': datetime.date.today().strftime('%d.%m.%Y'),
}
out = tpl_site.replace('/*SITE*/null', json.dumps(site, ensure_ascii=False).replace('</', '<\\/'))
(base / 'index.html').write_text(out, encoding='utf-8')
print('index.html gebaut:', len(firmen), 'Firmen,', round(len(out) / 1024), 'KB')
