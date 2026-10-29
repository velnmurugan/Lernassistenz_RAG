"""Offline-Test V19b (ohne Modell, ohne Ollama): prüft die zwei Parser-Korrekturen an den echten Rohausgaben von R07 und F62.
Aufruf im Ordner lernassistent:  python3 teste_v19b_offline.py   (Schalter wird hier selbst gesetzt)"""
import os, sys
os.environ["LERNASSISTENT_V19"] = "AB"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rechenbaustein as rb
rb.RB_V8 = True

R07 = """FORMEL: i(t) = I₀ * exp(-t / (R * C))
WERTE:
I_0 = <Symbol> <Einheit>
I_t = 0,25 * I_0 <Einheit>
t = 0,05 s <Einheit>
R = 2200 Ω <Einheit>
tau = - t / ln(I_t / I_0) <Einheit>
C = tau / R <Einheit>
RECHNUNG:
I_t = 0,25 * I_0
tau = - 0,05 / ln(0,25)
C = (- 0,05 / ln(0,25)) / 2200
ERGEBNIS: C
EINHEIT: F
QUELLE: i = U/R e^(-t/τ) mit τ = R C"""
F62 = """FORMEL: J_e = m_g (v/ω)²
WERTE:
m_g = 500 kg
v = 0,5 m/s
n = 1000/60 1/s
ω = 2*pi*n rad/s
RECHNUNG:
J_e = 500 * (0.5 / (2*pi*(1000/60)))**2 kg*m**2
ERGEBNIS: J_e
EINHEIT: kg*m**2
QUELLE: J_e = m_g (v/ω)²"""
FALL = [
 ("R07", R07, "Ein Kondensator wird über R = 2,2 kΩ aufgeladen. Nach t = 0,05 s beträgt der Ladestrom nur noch 25 % des Anfangswertes. Wie groß ist die Kapazität C?", "C", 1.6394e-05),
 ("F62", F62, "Masse 500 kg, v = 0,5 m/s bei n = 1000 1/min. Ersatzträgheitsmoment?", "J_e", 0.011399),
]
fehler = 0
for nr, roh, frage, name, soll in FALL:
    r = rb.rechne_v7(rb.parse_v7(roh), frage, "")
    erg = dict(r.get("ergebnisse") or [])
    ist = erg.get(name)
    ok = ist is not None and abs(ist - soll) <= 0.001 * soll
    print(f"{nr}: {'OK ' if ok else 'FEHLER'}  {name} = {ist}  (soll {soll})  grund={r.get('grund')!r}")
    fehler += not ok
print("ALLE TESTS BESTANDEN" if not fehler else f"{fehler} TEST(S) FEHLGESCHLAGEN")
sys.exit(1 if fehler else 0)
