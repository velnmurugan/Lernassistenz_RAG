"""DP-v1: Dimensionsprüfung der Python-Nachrechnung (gehört zu RB-v8).

Idee: Jede Größe der Nachrechnung trägt eine physikalische Dimension (Exponenten von Länge, Masse, Zeit, Strom, Temperatur,
Stoffmenge, Lichtstärke und Geld). Die Dimension wird durch FORMEL/WERTE/RECHNUNG mitgeführt, unabhängig vom Sprachmodell.
Widerspruch = (a) Summe/Differenz verschiedener Dimensionen, (b) berechneter Ausdruck ≠ angegebene Einheit derselben Zeile,
(c) Ergebnis ≠ Einheit unter EINHEIT. Unbekannt (Zahl ohne Einheit, unbekannte Einheit, nicht lesbarer Ausdruck) führt nie zu
einem Widerspruch; geprüft wird nur, was eindeutig ist.
Beispiel: eine Gewichtskraft durch g geteilt ergibt kg, angegeben ist N; die Zahlenprüfung erkennt das nicht, die Dimension schon.
Rückgabe von pruefe(roh): {"widerspruch": bool, "detail": str}."""
import ast
import re
from fractions import Fraction

import rechenbaustein as rb

# Basisdimensionen: L M T I Θ N J €
_NULL = (0,) * 8


def _d(L=0, M=0, T=0, I=0, K=0, N=0, J=0, E=0):
    return tuple(Fraction(x) for x in (L, M, T, I, K, N, J, E))


_LOS = _d()
_ATOM = {
    "m": _d(L=1), "g": _d(M=1), "s": _d(T=1), "A": _d(I=1), "K": _d(K=1), "mol": _d(N=1), "cd": _d(J=1),
    "V": _d(L=2, M=1, T=-3, I=-1), "W": _d(L=2, M=1, T=-3), "Ω": _d(L=2, M=1, T=-3, I=-2), "Ohm": _d(L=2, M=1, T=-3, I=-2),
    "N": _d(L=1, M=1, T=-2), "J": _d(L=2, M=1, T=-2), "Hz": _d(T=-1), "H": _d(L=2, M=1, T=-2, I=-2),
    "F": _d(L=-2, M=-1, T=4, I=2), "C": _d(T=1, I=1), "T": _d(M=1, T=-2, I=-1), "Wb": _d(L=2, M=1, T=-2, I=-1),
    "Pa": _d(L=-1, M=1, T=-2), "VA": _d(L=2, M=1, T=-3), "var": _d(L=2, M=1, T=-3), "€": _d(E=1), "bar": _d(L=-1, M=1, T=-2),
    "l": _d(L=3), "L": _d(L=3), "Wh": _d(L=2, M=1, T=-2), "Ah": _d(T=1, I=1), "Ws": _d(L=2, M=1, T=-2), "Nm": _d(L=2, M=1, T=-2),
    "VAh": _d(L=2, M=1, T=-2), "kg": _d(M=1), "S": _d(L=-2, M=-1, T=3, I=2), "rad": _LOS, "sr": _LOS,
}
_DIREKT = {"min": _d(T=1), "h": _d(T=1), "%": _LOS, "‰": _LOS, "rpm": _d(T=-1), "Nmm": _d(L=2, M=1, T=-2),
           "Ncm": _d(L=2, M=1, T=-2), "kNm": _d(L=2, M=1, T=-2), "Mio€": _d(E=1), "Mrd€": _d(E=1), "Mio": _LOS, "Mrd": _LOS,
           "t": _d(M=1), "°C": _d(K=1), "°": _LOS, "Grad": _LOS, "dB": _LOS, "1": _LOS, "kWh": _d(L=2, M=1, T=-2)}
_PRAEFIX = set("TGMkhdcmμµunp")
# Zahlen, die in Nachrechnungen fast immer für eine Naturkonstante stehen (ohne Einheit hingeschrieben)
_KONSTANTEN_WERTE = [(9.81, _d(L=1, T=-2)), (9.80665, _d(L=1, T=-2)), (1.2566370614e-06, _d(L=1, M=1, T=-2, I=-2)),
                     (1.256637e-06, _d(L=1, M=1, T=-2, I=-2)), (8.854e-12, _d(L=-3, M=-1, T=4, I=2)),
                     (1.602e-19, _d(T=1, I=1)), (1.6022e-19, _d(T=1, I=1))]
_STRUKTUR = {1.0, 2.0, 3.0, 4.0, 0.5, 0.25}


def _mal(a, b, k=1):
    return tuple(x + k * y for x, y in zip(a, b))


def _hoch(a, k):
    return tuple(x * k for x in a)


def _atom_dim(atom):
    m = re.fullmatch(r"(.+?)(?:\^|\*\*)?\(?([-−]?\d)?\)?", atom)
    kern, hoch = (m.group(1), m.group(2)) if m else (atom, None)
    if kern and kern[-1:] in "-−" and hoch is None:
        return None
    hoch = int((hoch or "1").replace("−", "-"))
    if kern in _DIREKT:
        d = _DIREKT[kern]
    elif kern in _ATOM:
        d = _ATOM[kern]
    elif len(kern) > 1 and kern[0] in _PRAEFIX and kern[1:] in _ATOM:
        d = _ATOM[kern[1:]]
    else:
        d = _zusammengeschrieben(kern)
    return None if d is None else _hoch(d, hoch)


def _zusammengeschrieben(kern):
    bekannt = sorted(_ATOM, key=len, reverse=True)

    def zerlege(rest, tiefe):
        if not rest:
            return _LOS
        if tiefe == 0:
            return None
        for b in bekannt:
            if rest.startswith(b):
                r = zerlege(rest[len(b):], tiefe - 1)
                if r is not None:
                    return _mal(r, _ATOM[b])
        return None
    return zerlege(kern, 3) if len(kern) >= 2 else None


def einheit_dim(einheit):
    """'Ω·mm²/m' -> Dimension von Ω·m; unbekannt -> None. Gleiche Zerlegung wie rechenbaustein.einheit_faktor_v7."""
    e = rb._nfkc(einheit or "").strip().rstrip(".,;:)").replace(" ", "").replace("Mio.", "Mio").replace("Mrd.", "Mrd")
    e = e.replace("U/min", "rpm").replace("1/min", "min-1").replace("1/s", "s-1").replace("*", "·").replace("×", "·")
    if not e:
        return None
    if e in _DIREKT:
        return _DIREKT[e]
    zaehler, _, nenner = e.partition("/")
    d = _LOS
    for teil, vz in ((zaehler, 1), (nenner, -1)):
        for atom in [x for x in teil.replace("(", "").replace(")", "").split("·") if x]:
            if atom == "1":
                continue
            a = _atom_dim(atom)
            if a is None:
                return None
            d = _mal(d, a, vz)
    return d


def zeige(d):
    if d is None:
        return "?"
    namen = ["m", "kg", "s", "A", "K", "mol", "cd", "€"]
    teile = [n + ("" if x == 1 else f"^{x}") for n, x in zip(namen, d) if x]
    return "·".join(teile) or "1"


class _Widerspruch(Exception):
    pass


_ZAHL_EINHEIT = rb._ZAHL_EINHEIT_V7


def _ausdruck_dim(ausdruck, dims, werte_zahlen=frozenset()):
    """Dimension eines Ausdrucks oder None (unbekannt). Wirft _Widerspruch bei Summe verschiedener bekannter Dimensionen.
    Zahlen ohne Einheit sind unbekannt (eingesetzte Werte, z. B. "0,5 * 0,5 * 4**2"). Ausnahme: kleine Strukturzahlen (2, 1/2 …) in
    einem Ausdruck mit Namen, wenn sie keinem Wert unter WERTE gleichen; Naturkonstanten (9,81 für g, μ₀, e) mit ihrer Dimension."""
    platz = {}

    def ersetze(m):
        d = einheit_dim(m.group(2))
        if d is None:
            return m.group(0)
        k = f"__q{len(platz)}"
        platz[k] = d
        return k
    t = _ZAHL_EINHEIT.sub(ersetze, rb._latex_weg(rb._nfkc(ausdruck)))
    t = rb.normiere_ausdruck(re.sub(r"(?<=\d),(?=\d)", ".", t))
    try:
        baum = ast.parse(t, mode="eval")
    except SyntaxError:
        return None
    alle = {**dims, **platz}
    mit_namen = any(isinstance(k, ast.Name) and k.id != "pi" for k in ast.walk(baum))

    def w(k):
        if isinstance(k, ast.Expression):
            return w(k.body)
        if isinstance(k, ast.Constant) and isinstance(k.value, (int, float)) and not isinstance(k.value, bool):
            v = abs(float(k.value))
            if v in _STRUKTUR and mit_namen and round(v, 9) not in werte_zahlen:
                return _LOS
            for c, d in _KONSTANTEN_WERTE:
                if abs(v - c) <= 1e-3 * c:
                    return d
            return None
        if isinstance(k, ast.Name):
            if k.id == "pi":
                return _LOS
            return alle.get(k.id)
        if isinstance(k, ast.UnaryOp):
            return w(k.operand)
        if isinstance(k, ast.BinOp):
            a, b = w(k.left), w(k.right)
            if isinstance(k.op, (ast.Add, ast.Sub)):
                if a is not None and b is not None and a != b:
                    raise _Widerspruch(f"Summe aus {zeige(a)} und {zeige(b)}")
                return a if a is not None else b
            if isinstance(k.op, ast.Mult):
                return None if a is None or b is None else _mal(a, b)
            if isinstance(k.op, ast.Div):
                return None if a is None or b is None else _mal(a, b, -1)
            if isinstance(k.op, ast.Pow):
                if a is None:
                    return None
                ex = k.right
                neg = isinstance(ex, ast.UnaryOp) and isinstance(ex.op, ast.USub)
                ex = ex.operand if neg else ex
                if isinstance(ex, ast.Constant) and isinstance(ex.value, (int, float)):
                    return _hoch(a, Fraction(ex.value).limit_denominator(12) * (-1 if neg else 1))
                return None if any(a) else _LOS
            return None
        if isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and len(k.args) == 1:
            a = w(k.args[0])
            if k.func.id == "sqrt":
                return None if a is None else _hoch(a, Fraction(1, 2))
            if k.func.id == "abs":
                return a
            return _LOS  # Winkel-, Exponential- und Logarithmusfunktionen: Ergebnis ohne Dimension
        return None
    return w(baum)


def _ausdruck_und_einheit(text):
    """WERTE-Zeile "Ausdruck Einheit": 'rho * g * l * Q kg*m/s²' -> ('rho * g * l * Q', 'kg*m/s²'); 'F_m / 9,81 N' -> ('F_m / 9,81', 'N').
    Eine einzelne Zahl mit Einheit ('7800 kg/m³') bleibt zusammen (Einheit gehört zur Zahl)."""
    text = text.strip()
    teile = text.rsplit(None, 1)
    ist_ausdruck = len(teile) == 2 and (re.search(r"[*/+\-^()]", teile[0]) or re.search(rf"{rb._NAME_V6}", re.sub(r"\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?", "", teile[0])))
    if ist_ausdruck and einheit_dim(teile[1]) is not None:
        try:
            ast.parse(rb.normiere_ausdruck(re.sub(r"(?<=\d),(?=\d)", ".", rb._latex_weg(rb._nfkc(teile[0])))), mode="eval")
            return teile[0], teile[1]
        except SyntaxError:
            pass
    return text, None


def pruefe(roh):
    """Dimensionsprüfung einer Nachrechnung (Rohtext mit FORMEL/WERTE/RECHNUNG/ERGEBNIS/EINHEIT)."""
    try:
        text = rb._latex_weg(rb._nfkc(roh or "")).replace("≈", "=")
        a = rb._abschnitte_v6(text)
        dims = {}
        werte_zahlen = set()
        for _, wert in rb._zuweisungen_v6(a.get("WERTE", ""), False):
            m = re.match(r"\s*([-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)\s*\S*\s*$", wert)
            if m:
                werte_zahlen.add(round(float(m.group(1).replace(",", ".")), 9))
        for block, rechnung in ((a.get("WERTE", ""), False), (a.get("RECHNUNG", ""), True)):
            for name, wert in rb._zuweisungen_v6(block, rechnung):
                wert = wert.split("=")[-1].strip() if "=" in wert else wert  # Kettenzeile: letzter Teil
                ausdruck, angabe = _ausdruck_und_einheit(wert)  # auch in RECHNUNG steht manchmal eine Einheit am Ende
                try:
                    d = _ausdruck_dim(ausdruck, dims, frozenset(werte_zahlen))
                except _Widerspruch as e:
                    return {"widerspruch": True, "detail": f"{name}: {e}"}
                da = einheit_dim(angabe) if angabe else None
                if d is not None and da is not None and d != da:
                    return {"widerspruch": True, "detail": f"{name} = {ausdruck} hat die Dimension {zeige(d)}, angegeben ist {angabe}"}
                neu = da if da is not None else d
                if neu is not None or name not in dims:
                    dims[name] = neu
        zeile = a.get("ERGEBNIS", "").splitlines()[0] if a.get("ERGEBNIS") else ""
        ergebnisse = [rb._nfkc(x.strip()) for x in re.split(r"[,;]|\bund\b", zeile) if x.strip()]
        einheiten = [e.strip() for e in re.split(r"[,;]", (a.get("EINHEIT", "").splitlines() or [""])[0]) if e.strip()]
        if ergebnisse and len(einheiten) == len(ergebnisse):
            for n, e in zip(ergebnisse, einheiten):
                d, de = dims.get(n), einheit_dim(e)
                if d is not None and de is not None and d != de:
                    return {"widerspruch": True, "detail": f"Ergebnis {n} hat die Dimension {zeige(d)}, gefragt ist {e}"}
        return {"widerspruch": False, "detail": ""}
    except Exception as e:  # Prüfung darf nie scheitern lassen
        return {"widerspruch": False, "detail": f"Prüfung nicht möglich: {e}"}
