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

RP-v2 (V10, 19 Oct 2026) = RP-v1 + zwei weitere deterministische Prüfungen (pruefe(text, frage, version)):
  - Konsistenz: Der Wert im ersten Satz (Ergebnis-Satz nach L2) muss zum Endergebnis der letzten Rechnung
    passen (auch als Prozent: 0,05 = 5 %). Anlass Q13 (Lauf V9D): "Der Schlupf beträgt 0,02 oder 2 %" im
    ersten Satz, die Rechnung danach ergibt 0,05; RP-v1 meldete "ok", weil keine Gleichung falsch war.
  - Sichtbare Überlegung: Selbstkorrekturen und Abwägungen in der Lösung ("Rechenfehler", "korrigieren",
    "Warte", "Entscheidung:", "STATUS:"). Anlass Q13 und Q27 (Lauf V9D).
Beide Befunde werden wie RP-v1 behandelt (ein Neuschreib-Aufruf, sonst sichtbarer Vermerk).

RP-v3 (V10a, 19 Oct 2026) = RP-v2 + Variablennamen mit Index ("P1", "U2", "R20") werden nicht mehr als Zahl
gelesen. Anlass Q27 (Lauf V10): "P1 = 4000 W / 0,815 = 4908 W" ergab den falschen Vermerk
"4000 / 0,815 ergibt 4908, nicht 1" (die "1" aus "P1"). Folge davon: Ein Ausdruck, der über einen Operator an ein
Symbol grenzt ("R20 · (1 + 0,004 · 30)"), wird nicht mehr nur zur Hälfte gelesen (sonst falscher Befund).
RP-v1 und RP-v2 bleiben unverändert (Reproduzierbarkeit).

RP-v5 (V11b, 21 Oct 2026) = RP-v3 + Namen mit Unterstrich-Index ("I_1N", "U_2N", "u_k") werden als ein Variablenname
gelesen. Anlass: Live-Test "Bemessungsstrom 40 kVA / 5 kV": die Vermerke "(40) / (√3 · 5) ergibt 4,619, nicht 1" und
"… nicht 2" stammen aus der "1" in "I_1N" und der "2" in "I_2N". RP-v3 und RP-v4 bleiben unverändert.
"""
import ast
import math
import operator
import re

RECHEN_PRUEFUNG_VERSION = "RP-v3"  # Bezeichnung; Schalter ist rag_pipeline.RECHEN_PRUEFUNG_VERSION

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


# RP-v3: Buchstabe + 1-2 Ziffern direkt daneben ("P1", "U2", "R20") ist ein Variablenname -> tiefgestellte Ziffern,
# die der Tokenizer als Teil des Wortes liest. Nur aktiv in pruefe(..., version="RP-v3"); sonst wie RP-v1/v2.
_INDEX_FIX = False
_UNTERSTRICH_FIX = False  # RP-v5: "I_1N", "U_2N", "u_k" -> ein Name (siehe pruefe)
_UNTERSTRICHNAME = re.compile(r"(?<![\w.,])([A-Za-zηφΦϑα-ωΑ-Ω]{1,3})_([A-Za-z0-9]{1,4})\b")
_INDEXNAME = re.compile(r"(?<![\w.,])([A-Za-zηφΦϑα-ωΑ-Ω])(\d{1,2})\b(?![,.]\d)")
_TIEF = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


_ZEHNERPOTENZ = re.compile(r"(?<![\d,.])10\s*\^\s*\(?\s*([-−–]?)\s*(\d{1,2})\s*\)?")


def _zehnerpotenz(m):
    """"10^18" -> eine Zahl (1000000000000000000), "10^-3" -> 0,001. V12: vorher las die Prüfung "10" und "18" als zwei
    Zahlen und meldete bei "3 · 6,25 · 10^18 = 18,75 · 10^18" fälschlich "18,75 · 10 ergibt 187,5, nicht 18" (N100 Nr 1)."""
    n = int(m.group(2))
    if m.group(1):
        return "0," + "0" * (n - 1) + "1" if n >= 1 else "1"
    return "1" + "0" * n


def _tokens(teil):
    teil = _ZEHNERPOTENZ.sub(_zehnerpotenz, teil)
    if _UNTERSTRICH_FIX:
        teil = _UNTERSTRICHNAME.sub(lambda m: m.group(1) + m.group(2).translate(_TIEF), teil)
    if _INDEX_FIX:
        teil = _INDEXNAME.sub(lambda m: m.group(1) + m.group(2).translate(_TIEF), teil)
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
    folge, stopp = [], None
    reihe = reversed(toks) if ende else iter(toks)
    for art, wert in reihe:
        if art not in _ERLAUBT:
            stopp = art
            break
        folge.append((art, wert))
    if ende:
        folge.reverse()
    # RP-v3: grenzt der Ausdruck über einen Operator an ein Symbol ("R20 · (1 + 0,004 · 30)", "0,02 · R20"),
    # ist nur ein Teil des Produkts zu sehen; dann nicht prüfen statt die Hälfte zu rechnen
    if _INDEX_FIX and stopp == "wort" and folge and folge[0 if ende else -1][0] == "op":
        return None
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
    if not stellen:  # nur ganze Zahlen mit Endnullen
        toleranz = min(toleranz, 0.10 * abs(angegeben))  # V12.2: "100" gilt nicht für 75 (A/B F55: ±50 war zu weit)
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
    if abs(x) >= 1e9 or abs(x) < 1e-6:  # V12: Zehnerpotenz-Schreibweise statt 19-stelliger Zahl
        m, e = f"{x:.4e}".split("e")
        return f"{m.rstrip('0').rstrip('.').replace('.', ',')}·10^{int(e)}"
    stellen = max(0, 3 - int(math.floor(math.log10(abs(x)))))
    t = f"{x:.{min(stellen, 6)}f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


def _anzeige_potenz(text):
    """Lange Ziffernfolgen aus _zehnerpotenz() zurück in die Anzeige: 1000000000000000000 -> 10^18."""
    return re.sub(r"(?<![\d,.])1(0{6,})(?![\d])", lambda m: f"10^{len(m.group(1))}", text or "")


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
                ausdruck = _anzeige_potenz(ausdruck)
                befunde.append({"ausdruck": ausdruck, "gerechnet": gerechnet, "angegeben": angegeben,
                                "satz": zeile.strip()[:200],
                                "text": f"{ausdruck} ergibt {_zahl_de(gerechnet)}, nicht {_zahl_de(angegeben)}"})
    return befunde


# ---------------------------------------------------------------------------------------------------------
# RP-v2 (V10): Konsistenz Ergebnis-Satz vs. Endergebnis, sichtbare Überlegung
# ---------------------------------------------------------------------------------------------------------
# Wörter und Feldnamen, die in einer fertigen Lösung nicht vorkommen sollen. Bewusst eng gefasst:
# "Korrektur" nur am Zeilenanfang oder nach "*"/"(" (nicht "Korrekturfaktor", nicht "eine Korrektur der
# Temperatur"), "Warte" nur mit Satzzeichen danach, "Moment" nur als "momentan habe ich" (sonst Drehmoment).
UEBERLEGUNG_SICHTBAR = re.compile(
    r"\b(?:rechenfehler\w*|verrechnet|momentan habe ich|ich habe mich (?:geirrt|vertan)|"
    r"(?:ich|wir) korrigiere\w*|korrigiere (?:ich|wir|mich|das)|lass(?:t)? uns (?:das |dies )?korrigieren|"
    r"wiederholtes (?:überprüfen|prüfen)|(?:über)?prüfen wir|"
    r"(?:noch ?mal|noch einmal)\s+(?:nachrechn|nachprüf|nachseh|überprüf|überleg|gerechnet|geprüft)\w*)\b"
    r"|(?:^|[\n*(])\s*korrektur\b|\bwarte\b\s*[,.!:…]|\b(?:entscheidung|status|überlegung|ueberlegung)\s*:",
    re.I)
# 19 Oct 2026: "korrigiert werden muss" (Temperaturkorrektur, Antwort ohne RAG zu T1) ist Fachsprache und
# zählt nicht; gezählt werden nur Selbstkorrekturen in der 1. Person und "Korrektur" am Zeilenanfang.

# Verweise und Normbezeichnungen enthalten Zahlen, die kein Ergebnis sind ("Beispiel 4.15", "Abb. 5.2",
# "DIN VDE 0100-410").
_VERWEIS_ZAHL = re.compile(r"\b(?:Beispiel|Bsp\.|Abb\.|Abbildung|Bild|Tab\.|Tabelle|Kapitel|Kap\.|Abschnitt|"
                           r"Gl\.|Gleichung|Seite|S\.)\s*\d+(?:[.,]\d+)*"
                           r"|\b(?:DIN|VDE|EN|IEC|ISO)\b(?:\s*[A-Z]*\s*[\d][\d\-./]*)+", re.I)
_ZAHL_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
# Abkürzungen mit Punkt, die keinen Satz beenden ("ca. 23 A", "z. B.", "bzw.")
_ABKUERZUNGEN = {"ca", "bzw", "bspw", "ggf", "evtl", "vgl", "inkl", "exkl", "max", "min", "mind", "nr", "abb",
                 "tab", "gl", "bsp", "kap", "usw", "etc", "sog", "zzgl", "ugs", "allg", "insb", "jew", "rd", "ab"}


def _erster_satz_ende(text):
    """Position des ersten Satzendes (Punkt + Leerraum oder Zeilenumbruch), Abkürzungen ausgenommen."""
    for m in re.finditer(r"\.(?=\s)|\n", text):
        if m.group(0) == "\n":
            return m
        davor = re.search(r"(\S+)$", text[:m.start()])
        wort = davor.group(1) if davor else ""
        if re.search(r"\d$", wort):          # Zahl am Satzende ("… beträgt 0,05.")
            return m
        w = wort.lower().strip("(„\"")
        if w in _ABKUERZUNGEN or re.fullmatch(r"(?:[a-zäöü]\.)+[a-zäöü]", w):
            continue
        # zweiteilige Abkürzungen "z. B.", "d. h.", "u. a.", "z. T.", "o. ä.", "u. U.", "i. d. R."
        if w in ("z", "d", "u", "o", "i") and re.match(r"\s?[A-Za-zÄÖÜäöü]\.", text[m.end():]):
            continue                              # erster Teil ("z.")
        if len(w) == 1 and re.search(r"\b[zduoi]\.\s?$", text[:m.start() - len(wort)]):
            continue                              # zweiter Teil ("B.")
        return m                                  # sonst Satzende, auch nach Einheiten wie "A", "V", "°C"
    return None


def _endergebnis(text):
    """Letzter echter Rechenschritt im Text: rechte Seite eines "=" / "≈", dessen linke Seite rechnet
    (Operator zwischen Zahlen) und dessen rechte Seite eine einfache Zahl ist. Reine Angaben wie
    "I = 2 A" zählen nicht. Rückgabe (Wert, Text, Nachkommastellen) oder None."""
    letztes = None
    for zeile in re.split(r"[\n;]|(?<=[a-zäöüß)])\.\s|(?<=\D)\.\s", text or ""):
        teile = _GLEICH.split(zeile)
        if len(teile) < 2:
            continue
        toks = [_tokens(t) for t in teile]
        for i in range(len(teile) - 1):
            links, rechts = _rand(toks[i], ende=True), _rand(toks[i + 1], ende=False)
            if links and rechts and not links[3] and rechts[3]:
                letztes = (rechts[0], rechts[1], rechts[2])
    return letztes


def _stellen(t):
    return len(re.split(r"[,.]", t)[1]) if re.search(r"[,.]\d+$", t) and not re.fullmatch(
        r"[1-9]\d{0,2}(?:\.\d{3})+", t) else 0


def _zahlen_mit_stellen(text):
    out = []
    for t in _ZAHL_TOKEN.findall(_VERWEIS_ZAHL.sub(" ", text or "")):
        try:
            out.append((abs(zahl(t)), _stellen(t), t))
        except ValueError:
            pass
    return out


def pruefe_konsistenz(text, frage=""):
    """Befund, wenn der erste Satz einen Wert nennt, der nicht zum Endergebnis der letzten Rechnung passt.
    Übersprungen, wenn der erste Satz keine eigene Zahl enthält (Zahlen aus der Frage zählen nicht) oder
    nach dem ersten Satz keine Rechnung mit Ergebnis folgt."""
    text = text or ""
    m = _erster_satz_ende(text)
    if not m:
        return []
    kopf, rest = text[:m.start()], text[m.end():]
    aus_frage = {w for w, _, _ in _zahlen_mit_stellen(frage)}
    kopf_zahlen = [(w, st, t) for w, st, t in _zahlen_mit_stellen(kopf) if w not in aus_frage]
    end = _endergebnis(rest)
    if not kopf_zahlen or not end:
        return []
    ende, t_end = abs(end[0]), end[1]
    for w, st, _ in kopf_zahlen:
        if any(_passt(kandidat, w, st) for kandidat in (ende, ende * 100, ende / 100)):
            return []
    genannt = " / ".join(t for _, _, t in kopf_zahlen[:3])
    return [{"art": "konsistenz", "ausdruck": "", "gerechnet": ende, "angegeben": kopf_zahlen[0][0],
             "satz": kopf.strip()[:200],
             "text": f"Der erste Satz nennt {genannt}, die Rechnung ergibt aber {t_end}"}]


def pruefe_ueberlegung(text):
    """Befund, wenn die Lösung sichtbare Zwischenüberlegungen oder Selbstkorrekturen enthält."""
    funde = [m.group(0).strip() for m in UEBERLEGUNG_SICHTBAR.finditer(text or "")]
    if not funde:
        return []
    beispiele = ", ".join(f"„{f}“" for f in list(dict.fromkeys(funde))[:3])
    return [{"art": "ueberlegung", "ausdruck": "", "gerechnet": None, "angegeben": None, "satz": "",
             "text": f"Die Lösung enthält sichtbare Zwischenüberlegungen oder Korrekturen ({beispiele}); "
                     f"sie soll nur das Ergebnis und die Begründung zeigen"}]


def pruefe(text, frage="", version="RP-v3"):
    """Alle Befunde der gewählten Version. RP-v1 = nur pruefe_rechnungen (unverändert); RP-v2 = + Konsistenz und
    sichtbare Überlegung; RP-v3 = RP-v2 mit Indexnamen-Korrektur; RP-v4 wie RP-v3; RP-v5 = RP-v3 + Unterstrich-Namen."""
    global _INDEX_FIX, _UNTERSTRICH_FIX
    alt, _INDEX_FIX = _INDEX_FIX, version not in ("RP-v1", "RP-v2")
    alt_u, _UNTERSTRICH_FIX = _UNTERSTRICH_FIX, version == "RP-v5"
    try:
        befunde = pruefe_rechnungen(text)
        if version != "RP-v1":
            befunde += pruefe_konsistenz(text, frage) + pruefe_ueberlegung(text)
    finally:
        _INDEX_FIX, _UNTERSTRICH_FIX = alt, alt_u
    return befunde
