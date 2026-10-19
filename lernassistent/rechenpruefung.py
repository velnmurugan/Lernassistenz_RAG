"""
rechenpruefung.py
-----------------
Rechenprüfung RP-v1 (V9d, 14 Oct 2026): prüft Gleichungsketten in einer Lösung ("A = B = C", auch "≈")
und meldet Schritte, deren Zahlenwerte nicht zusammenpassen. Python rechnet, nicht das Modell.

Anlass: Q13 (Schlupf) — die Lösung schrieb "(1500 − 1425) / 1500 = 75 / 1500 = 0,02" (richtig 0,05).
Das Modell kann seine eigene Rechnung nicht zuverlässig prüfen; ein Rechenschritt mit Zahlen lässt sich
aber deterministisch nachrechnen.

Vorgehen je Gleichungskette:
  1. Einheiten entfernen (Wort direkt nach einer Zahl, Einheitenbrüche wie "K/W", "1/min", "m/s²").
  2. Aus jedem Teil den rechenbaren Ausdruck am Rand nehmen (Ende des linken Teils, Anfang des rechten).
  3. Beide Seiten auswerten (nur Zahlen, + − · / ^, √, Hochzahlen, %, π; sicher über ast, kein eval).
  4. Abweichung > Toleranz -> Befund. Toleranz: 2 % relativ oder die Rundung der angegebenen Zahl.
Teile ohne Zahlen ("s", "η", "P₂ / P₁") werden übersprungen. Erkennt nur Fehler in ausgeschriebenen
Rechenschritten, keine falsch gewählte Formel und keine Zahl ohne Rechnung.
"""
import ast
import math
import operator
import re

RECHEN_PRUEFUNG_VERSION = "RP-v1"

_HOCH = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8",
         "⁹": "9", "⁻": "-"}
# Einheitenbrüche und Kehrwert-Einheiten vorab entfernen (sonst "1500 1/min" = zwei Zahlen hintereinander)
_EINHEIT_KEHRWERT = re.compile(r"(?<![\d,.])\b1\s*/\s*(?:min|s|h|K)\b|\b(?:min|s|h)\s*⁻\s*¹|\bU\s*/\s*min\b")
_EINHEITENBRUCH = re.compile(r"(?<=[A-Za-zΩµμ°²³])\s*/\s*[A-Za-zΩµμ°]+[²³]?")
_TOKEN = re.compile(r"\s*(?:(?P<zahl>\d+(?:[.,]\d+)*)|(?P<hoch>[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)|(?P<op>[-+−–·*×/÷^])|"
                    r"(?P<auf>\()|(?P<zu>\))|(?P<wurzel>√)|(?P<pi>π)|(?P<prozent>%)|"
                    r"(?P<wort>[A-Za-zÄÖÜäöüßΩµμ°α-ωΑ-ΩϑφΦ_₀₁₂₃₄₅₆₇₈₉']+)|(?P<rest>\S))")
_GLEICH = re.compile(r"\s*(?:=|≈)\s*")
# Einheiten (mit SI-Vorsatz) und Einheitenwörter; nur solche Wörter nach einer Zahl werden entfernt, damit
# "1425 hat s" nicht als "1425 [Einheit] [Einheit]" gelesen wird.
_EINHEIT = re.compile(r"(?:[pnµμmcdkMGT]?(?:m|s|g|A|V|W|Ω|Hz|N|J|K|C|F|H|T|Wb|S|Pa|bar|h|l|VA|var|VAr|Wh|"
                      r"rad|lm|lx|cd|mol|Nm|Ws|As|Vs|Ah|t)|°C|°|min|Ohm|dB|U|Grad|"
                      r"Volt|Ampere|Watt|Hertz|Kelvin|Newton|Joule|Meter|Sekunden?|Minuten?|Stunden?)")


def zahl(text):
    """Deutsche Schreibweise: Komma = Dezimaltrenner; Punkt = Tausender bei "76.200", sonst Dezimalpunkt."""
    t = text.strip()
    if "," in t:
        return float(t.replace(".", "").replace(",", "."))
    if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", t):
        return float(t.replace(".", ""))
    return float(t)


def _tokens(teil):
    teil = _EINHEITENBRUCH.sub("", _EINHEIT_KEHRWERT.sub(" ", teil))
    out = []
    for m in _TOKEN.finditer(teil):
        art = m.lastgroup
        out.append((art, m.group(art)))
    # Einheiten = Wörter direkt nach Zahl, Klammer zu, Hochzahl, Prozent oder anderer Einheit -> entfernen
    sauber, vorher = [], None
    for art, wert in out:
        if art == "wort" and vorher in ("zahl", "zu", "hoch", "prozent", "einheit") and _EINHEIT.fullmatch(wert):
            vorher = "einheit"
            continue
        if art == "hoch" and vorher == "einheit":  # "mm²", "m⁻¹": Hochzahl gehört zur Einheit
            continue
        sauber.append((art, wert))
        vorher = art
    return sauber


_ERLAUBT = {"zahl", "hoch", "op", "auf", "zu", "wurzel", "pi", "prozent"}


def _ausdruck_text(toks):
    """Tokens -> Python-Ausdruck (nur Zahlen und Operatoren) oder None."""
    py, vorher = [], None
    for art, wert in toks:
        implizit = vorher in ("zahl", "zu", "pi", "hoch") and art in ("zahl", "wurzel", "pi", "auf")
        if implizit:
            if vorher == "zahl" and art == "zahl":
                return None  # zwei Zahlen ohne Operator: kein Rechenausdruck
            py.append("*")
        if art == "zahl":
            py.append(repr(zahl(wert)))
        elif art == "hoch":
            exp = "".join(_HOCH[c] for c in wert)
            if not re.fullmatch(r"-?\d+", exp):
                return None
            py.append(f"**({exp})")
        elif art == "op":
            py.append({"·": "*", "×": "*", "÷": "/", "−": "-", "–": "-", "^": "**"}.get(wert, wert))
        elif art == "auf":
            py.append("(")
        elif art == "zu":
            py.append(")")
        elif art == "wurzel":
            py.append("WURZEL")
        elif art == "pi":
            py.append(repr(math.pi))
        elif art == "prozent":
            py.append("/100")
        vorher = art
    text = " ".join(py)
    # √ wirkt auf die folgende Zahl oder Klammer
    text = re.sub(r"WURZEL \* ", "WURZEL ", text)
    text = re.sub(r"WURZEL (\d+(?:\.\d+)?(?:e[-+]?\d+)?)", r"sqrt(\1)", text)
    text = text.replace("WURZEL (", "sqrt((")  # Klammer bleibt ausgeglichen: sqrt((...)
    return None if "WURZEL" in text else text


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _auswerten(text):
    def w(k):
        if isinstance(k, ast.Expression):
            return w(k.body)
        if isinstance(k, ast.Constant) and isinstance(k.value, (int, float)):
            return float(k.value)
        if isinstance(k, ast.BinOp) and type(k.op) in _OPS:
            a, b = w(k.left), w(k.right)
            if isinstance(k.op, ast.Pow) and abs(b) > 12:
                raise ValueError("Exponent")
            return _OPS[type(k.op)](a, b)
        if isinstance(k, ast.UnaryOp) and type(k.op) in _OPS:
            return _OPS[type(k.op)](w(k.operand))
        if isinstance(k, ast.Call) and getattr(k.func, "id", "") == "sqrt" and len(k.args) == 1:
            return math.sqrt(w(k.args[0]))
        raise ValueError("nicht erlaubt")
    try:
        return w(ast.parse(text, mode="eval"))
    except Exception:
        return None


def _rand(toks, ende):
    """Rechenbarer Ausdruck am Ende (ende=True) bzw. Anfang eines Teils: (Wert, Text, Nachkommastellen)."""
    folge = []
    reihe = reversed(toks) if ende else iter(toks)
    for art, wert in reihe:
        if art not in _ERLAUBT:
            break
        folge.append((art, wert))
    if ende:
        folge.reverse()
    # so lange von außen kürzen, bis der Ausdruck auswertbar ist (unausgeglichene Klammern, Operator am Rand)
    for _ in range(len(folge)):
        if not any(a == "zahl" for a, _ in folge):
            return None
        text = _ausdruck_text(folge)
        wert = _auswerten(text) if text else None
        if wert is not None:
            anzeige = " ".join(v for _, v in folge)
            zahlen = [v for a, v in folge if a == "zahl"]
            stellen = len(re.split(r"[,.]", zahlen[-1])[1]) if re.search(r"[,.]\d+$", zahlen[-1]) else 0
            return wert, anzeige, stellen, len(folge) == 1 or (len(folge) == 2 and folge[1][0] == "prozent")
        folge = folge[1:] if ende else folge[:-1]
    return None


def _passt(gerechnet, angegeben, stellen):
    """Toleranz: halbe Einheit der letzten gültigen Ziffer der angegebenen Zahl ("400" -> ±50, "4882" -> ±0,5,
    "0,02" -> ±0,005), mindestens 0,5 % (gerundete Zwischenwerte wie √3 ≈ 1,73)."""
    if angegeben == 0:
        return abs(gerechnet) < 1e-9
    exponent = math.floor(math.log10(abs(angegeben)))
    if stellen:
        letzte = -stellen
    else:  # ganze Zahl: Nullen am Ende zählen nicht als gültige Ziffern
        z = str(int(round(abs(angegeben))))
        letzte = len(z) - len(z.rstrip("0")) if z.rstrip("0") else exponent
    toleranz = max(0.5 * 10 ** letzte, 0.005 * abs(angegeben), 1e-12)
    if abs(gerechnet - angegeben) <= toleranz:
        return True
    # Faktor 10³, 10⁶ … : vermutlich stillschweigende Umrechnung von Vorsätzen (µF -> F, mm -> m),
    # kein Rechenfehler; Einheitenfehler sind nicht Aufgabe dieser Prüfung
    if gerechnet and angegeben:
        q = math.log10(abs(angegeben / gerechnet))
        if abs(q) >= 2.5 and abs(q - round(q)) < 0.01 and round(q) % 3 == 0:
            return True
    return False


def _zahl_de(x):
    if x == 0:
        return "0"
    stellen = max(0, 3 - int(math.floor(math.log10(abs(x)))))
    t = f"{x:.{min(stellen, 6)}f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


def pruefe_rechnungen(text):
    """Liste von Befunden {ausdruck, gerechnet, angegeben, satz}; leer = keine erkannte Abweichung."""
    befunde = []
    for zeile in re.split(r"[\n;]|(?<=[a-zäöüß)])\.\s|(?<=\D)\.\s", text or ""):
        teile = _GLEICH.split(zeile)
        if len(teile) < 2:
            continue
        toks = [_tokens(t) for t in teile]
        for i in range(len(teile) - 1):
            links, rechts = _rand(toks[i], ende=True), _rand(toks[i + 1], ende=False)
            if not links or not rechts:
                continue
            (wl, al, sl, l_einfach), (wr, ar, sr, r_einfach) = links, rechts
            if l_einfach and r_einfach:
                continue  # Zahl = Zahl (z. B. "0,05 = 5 %") nur prüfen, wenn eine Seite rechnet
            # die Seite mit der Rechnung ist "gerechnet", die einfache Zahl ist "angegeben"
            if r_einfach:
                gerechnet, angegeben, stellen, ausdruck = wl, wr, sr, al
            elif l_einfach:
                gerechnet, angegeben, stellen, ausdruck = wr, wl, sl, ar
            else:
                gerechnet, angegeben, stellen, ausdruck = wl, wr, 0, f"{al} = {ar}"
            if not _passt(gerechnet, angegeben, stellen):
                befunde.append({"ausdruck": ausdruck, "gerechnet": gerechnet, "angegeben": angegeben,
                                "satz": zeile.strip()[:200],
                                "text": f"{ausdruck} ergibt {_zahl_de(gerechnet)}, nicht {_zahl_de(angegeben)}"})
    return befunde
