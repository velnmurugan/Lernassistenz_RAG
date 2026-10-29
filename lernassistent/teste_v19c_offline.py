"""Offline-Test V19c (ohne Modell): Ziffer 1 in LERNASSISTENT_V19 begrenzt die ergänzten Formel-Chunks auf 1, sonst bleiben es 2."""
import os, sys, subprocess, json
HIER = os.path.dirname(os.path.abspath(__file__))
KOD = r'''
import sys, os, json
sys.path[:0] = [%r, os.path.join(%r, "lernassistent")]
import formelsuche as fs
fs.parse_weg = lambda roh: ["Begriff eins", "Begriff zwei"]
chunks = [{"id": "c%%d" %% i, "thema": "t", "text": "U = R * I und P = U * I Nummer %%d" %% i, "score": 1.0} for i in range(8)]
def retr(phrase, ch, top_k=6, methode=None):
    return ch[:3], ch
zusatz, info = fs.suche_v19("frage", chunks, [chunks[7]], retr, lambda p, options=None: "x", bewerte_fn=lambda q, ts: [float(i) for i in range(len(ts))])
print(json.dumps({"n": len(zusatz), "z": fs.V19_ZUSATZ, "fehler": info["fehler"]}))
''' % (HIER, HIER)
fehler = 0
for wert, soll in (("AB1", 1), ("A1", 1), ("AB", 2), ("A", 2)):
    out = subprocess.run([sys.executable, "-I", "-c", KOD], env={**os.environ, "LERNASSISTENT_V19": wert}, capture_output=True, text=True)
    try:
        d = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        print("FEHLER bei", repr(wert), out.stdout[-200:], out.stderr[-300:]); fehler += 1; continue
    ok = d["n"] == soll and d["z"] == soll and not d["fehler"]
    print(f"V19={wert!r:6}: ergänzt {d['n']} (soll {soll}), V19_ZUSATZ={d['z']} -> {'OK' if ok else 'FEHLER'}")
    fehler += not ok
print("ALLE TESTS BESTANDEN" if not fehler else f"{fehler} TEST(S) FEHLGESCHLAGEN")
sys.exit(1 if fehler else 0)
