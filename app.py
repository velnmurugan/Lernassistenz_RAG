"""
app.py
------
Lernassistent – Lernoberfläche (Streamlit).

Ablauf:
  1. Sitzungs-ID eingeben (pseudonymisiert, keine Klarnamen)
  2. Fragen an den Lernassistenten stellen (beliebig viele)
     Pro Antwort: Hinweis -> optional "Deine Idee?" mit Rückmeldung
     (ideen_feedback.py) -> Lösung mit Begründung
  3. Abschließenden Fragebogen ausfüllen (TAM-basiert, Davis 1989)

Start: bash skripte/laeufe/start_demo.sh  (setzt die Umgebungsvariablen von V20)
(Ollama muss laufen, Modell: qwen3.5:9b)
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import glob
import re
import time
import streamlit as st
try:
    import fitz  # PyMuPDF: Buchseiten als Bild (optional; ohne PyMuPDF entfällt nur diese Anzeige)
except Exception:  # pragma: no cover
    fitz = None
from rag_pipeline import (
    lade_wissensbasis, beantworte_frage, protokolliere_interaktion,
    speichere_fragebogen, FRAGEBOGEN_ITEMS,
)
from ideen_feedback import gib_feedback, protokolliere_idee, idee_moeglich, MAX_VERSUCHE
import lernhilfen
from bildeingabe import bildeingabe_ui, chat_eingabe

APP_NAME = "KI-Lernassistent"  # Arbeitsname, an einer Stelle änderbar

st.set_page_config(page_title=APP_NAME, page_icon="🎓", layout="centered", initial_sidebar_state="expanded")

if "seite" not in st.session_state:
    st.session_state["seite"] = "start"
if "verlauf" not in st.session_state:
    st.session_state["verlauf"] = []
if "sitzungs_id" not in st.session_state:
    st.session_state["sitzungs_id"] = ""

import os as _os, rag_pipeline as _rp  # Wissensbasis/Retrieval per Umgebungsvariable
# Konfiguration über Umgebungsvariablen (LERNASSISTENT_KB, LERNASSISTENT_RETRIEVAL, …), z. B. für ein einzelnes Buch:
#   LERNASSISTENT_KB=daten/wissensbasen/knowledge_base_boege.json streamlit run app.py ...
KB_OPTIONEN = {  # Anzeigename -> Datei (nur vorhandene Dateien erscheinen in der Auswahl)
    "Beide Bücher": "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json",  # Fischer + Böge, 8.805 Chunks
    "Beide Bücher, alt (Böge pypdf)": "daten/wissensbasen/knowledge_base_fischer_boege.json",
    "Fischer – Elektrotechnik": "daten/wissensbasen/knowledge_base_fischer_v7c.json",
    "Böge – Handbuch": "daten/wissensbasen/knowledge_base_boege.json",
}
KB_OPTIONEN = {n: p for n, p in KB_OPTIONEN.items() if _os.path.exists(p)}
_standard_kb = _os.environ.get("LERNASSISTENT_KB")
if _standard_kb and _standard_kb not in KB_OPTIONEN.values():
    KB_OPTIONEN[_os.path.basename(_standard_kb)] = _standard_kb
_namen = list(KB_OPTIONEN)
_start = next((n for n in _namen if KB_OPTIONEN[n] == _standard_kb), None) or next(
    (n for n in _namen if n.startswith("Beide")), _namen[0])
RETRIEVAL = _os.environ.get("LERNASSISTENT_RETRIEVAL", "hybrid_kg_rr")

# Normalbetrieb: immer die kombinierte Wissensbasis (alle Bücher), keine Auswahl für Lernende.
# Entwicklermodus (LERNASSISTENT_DEV=1): Einzelbücher zum Vergleich wählbar.
if _os.environ.get("LERNASSISTENT_DEV") == "1":
    with st.sidebar:
        st.header("Lernmaterial (Entwickler)")
        kb_name = st.selectbox("Durchsuchte Bücher", _namen, index=_namen.index(_start), key="kb_wahl",
                               help="Ein Wechsel startet ein neues Gespräch.")
else:
    kb_name = _start
KB_PFAD = KB_OPTIONEN[kb_name]
if st.session_state.get("kb_aktiv", KB_PFAD) != KB_PFAD:  # Wechsel: altes Gespräch verwerfen
    for k in [k for k in st.session_state if k.startswith(("stufe_", "ideen_", "idee_text_"))]:
        del st.session_state[k]
    st.session_state["verlauf"] = []
st.session_state["kb_aktiv"] = KB_PFAD
_rp.RETRIEVAL_METHODE = RETRIEVAL
import bildabgleich as _ba
_ba.KB_PFAD = KB_PFAD  # optional


@st.cache_resource(show_spinner="Lade Lernmaterial und Modelle (einmalig; beim ersten Start mit beiden Büchern mehrere Minuten) …")
def lade_und_waerme_auf(kb_pfad, retrieval_methode):
    """Lädt die Wissensbasis und lädt alle Modelle einmal vor (Embedding, BM25, Graph, Reranker,
    Sprachmodell), damit die erste Frage nicht deutlich länger dauert als die folgenden."""
    chunks = lade_wissensbasis(kb_pfad)
    try:
        _rp.retrieval("Aufwärmen", chunks, top_k=1, methode=retrieval_methode)
        _rp.frage_llm("Antworte nur mit: ok", options=_rp.GENERIERUNGS_OPTIONEN)
    except Exception as e:  # Aufwärmen darf den Start nie verhindern
        print(f"WARNUNG Aufwärmen: {e}")
    return chunks


CHUNKS = lade_und_waerme_auf(KB_PFAD, RETRIEVAL)


# =============================================================================
# SEITE 1: Start / Einverständnis / Sitzungs-ID
# =============================================================================
def seite_start():
    """Kurze Startseite: so funktioniert's in vier Schritten, Name eingeben, los."""
    st.title(f"🎓 {APP_NAME}")
    st.markdown("Dein Lernbegleiter für **Elektrotechnik** und **Maschinenbau**. "
                "Er verrät nicht sofort die Lösung, sondern hilft dir, **selbst draufzukommen**.")
    schritte = [("❓", "Frage stellen", "zu einem Thema aus deinen Fachbüchern"),
                ("💡", "Hinweis lesen", "ein Denkanstoß – noch nicht die Lösung"),
                ("✍️", "Idee aufschreiben", "du bekommst eine kurze Rückmeldung"),
                ("📖", "Lösung ansehen", "mit Begründung und Buchseite")]
    karten = "".join(
        f"<div style='flex:1 1 140px;padding:12px 12px 10px;border-radius:12px;border:1px solid rgba(140,140,140,.3);"
        f"background:rgba(140,140,140,.07)'><div style='font-size:1.6rem;line-height:1'>{sym}</div>"
        f"<div style='font-weight:600;margin-top:6px'><span style='opacity:.55'>{i}.</span> {titel}</div>"
        f"<div style='font-size:.82rem;opacity:.75;margin-top:2px'>{text}</div></div>"
        for i, (sym, titel, text) in enumerate(schritte, start=1))
    st.markdown(f"<div style='display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 6px'>{karten}</div>",
                unsafe_allow_html=True)
    st.caption("Steht etwas nicht in den Büchern, sagt der Assistent das ehrlich, statt zu raten. "
               "🔒 Alles läuft lokal auf diesem Rechner.")
    st.text_input("Dein Name", key="sitzungs_id_eingabe", placeholder="z. B. Alex", max_chars=40)
    if st.button("Los geht's →", type="primary"):
        eingabe = st.session_state.get("sitzungs_id_eingabe", "").strip()
        if not eingabe:
            st.error("Bitte gib deinen Namen ein.")
        else:
            st.session_state["sitzungs_id"] = eingabe
            st.session_state["seite"] = "chat"
            st.rerun()


# =============================================================================
# SEITE 2: Frage-Antwort-Interaktion mit gestuftem Scaffolding
# =============================================================================
PHASEN = {  # (laufend, fertig)
    "suche": ("Suche im Lernmaterial", "Im Lernmaterial gesucht"),
    "antwort": ("Formuliere die Antwort", "Antwort formuliert"),
    "pruefung": ("Prüfe die Antwort", "Antwort geprüft"),
}


def sek(d):
    """Dauer lesbar: unter 10 s mit einer Nachkommastelle."""
    return f"{d:.1f}".replace(".", ",") + " s" if d < 10 else f"{d:.0f} s"


def fortschritt_anzeige(status):
    """Rückruf für beantworte_frage: eine Zeile pro Phase, die sich nach Abschluss mit der Dauer füllt."""
    zeilen = {}

    def rueckruf(phase, ereignis, dauer=None, daten=None):
        if ereignis == "quellen":  # gefundene Quellen sofort zeigen, während die Antwort entsteht
            if "quellen" not in zeilen:
                zeilen["quellen"] = status.empty()
            orte = []
            for c in (daten or []):
                ort = (f"{c['buch']} " if c.get("buch") else "") + (f"S. {c['seite']}" if c.get("seite") else "")
                if ort.strip() and ort.strip() not in orte:
                    orte.append(ort.strip())
            if orte:
                zeilen["quellen"].markdown("📎 Gefunden: " + " · ".join(orte))
            return
        if phase not in zeilen:
            zeilen[phase] = status.empty()
        if ereignis == "start":
            zeilen[phase].markdown(f"⏳ {PHASEN[phase][0]} …")
        else:
            zeilen[phase].markdown(f"✓ {PHASEN[phase][1]} · {sek(dauer)}")
    return rueckruf


PHASEN_KURZ = {"suche": "Suche", "antwort": "Antwort", "pruefung": "Prüfung"}


def zeige_zeiten(eintrag):
    """Zeit immer sichtbar – Gesamtzeit und Phasen in einer Zeile."""
    zeiten = eintrag.get("zeiten") or {}
    if not zeiten:
        return
    gesamt = sum(zeiten.values())
    phasen = " · ".join(f"{PHASEN_KURZ.get(p, p)} {sek(zeiten[p])}" for p in PHASEN if p in zeiten)
    st.markdown(f"<div style='font-size:.85rem;opacity:.8;margin:4px 0'>⏱ <b>{sek(gesamt)}</b> &nbsp;·&nbsp; {phasen}</div>",
                unsafe_allow_html=True)


def zerlege_loesung(text):
    """Trennt Antwort, Begründung und den Vermerk der automatischen Prüfung (steht am Ende,
    beginnt mit "⚠ Automatische ...")."""
    vermerk = None
    m = re.search(r"\n*⚠\s*(Automatische [^:\n]*:[^\n]*)\s*$", text)
    if m:
        vermerk = m.group(1).strip()
        text = text[:m.start()].rstrip()
    teile = re.split(r"\s*Begründung:\s*", text, maxsplit=1)
    antwort = teile[0].strip()
    begruendung = teile[1].strip() if len(teile) > 1 else ""
    return antwort, begruendung, vermerk


def zeige_loesung(loesung, markiert=False):
    """markiert: True / "markiert" -> Warnkopf; "ersetzt" -> Kopf "aus der Nachrechnung", nie das grüne Häkchen."""
    antwort, begruendung, vermerk = zerlege_loesung(loesung)
    if markiert == "ersetzt":
        st.markdown(f"🔁 **Lösung aus der Python-Nachrechnung (bitte mit dem Buch prüfen):** {antwort}")
    elif markiert == "denkmodus":
        st.markdown(f"◔ **Lösung (im Denkmodus neu gerechnet, bitte mit dem Buch prüfen):** {antwort}")
    elif markiert == "ungeprueft":
        st.markdown(f"◔ **Lösung (Rechnung konnte nicht nachgeprüft werden):** {antwort}")
    else:
        st.markdown(f"⚠️ **Lösung (rechnerisch nicht bestätigt):** {antwort}" if markiert else f"✅ **Lösung:** {antwort}")
    if begruendung:
        st.markdown(f"**Begründung:** {begruendung}")
    if vermerk:
        st.caption(f"🔍 {vermerk}")


_LATEX_ERSATZ = {r"\varPhi": "Φ", "varPhi": "Φ", r"\Phi": "Φ", r"\Omega": "Ω", r"\cdot": "·", r"\approx": "≈",
                 r"\sqrt": "√", r"\eta": "η", r"\vartheta": "ϑ", r"\pi": "π", r"\varphi": "φ"}


def bereinige_auszug(text):
    """Macht Rohtext aus der PDF-Extraktion lesbar: Silbentrennung am Zeilenende zusammenführen, Zeilenumbrüche
    mitten im Satz entfernen (kurze Tabellenzeilen bleiben einzeln), doppelte Zeilen (Tabellen stehen in der
    Extraktion teils zweimal) entfernen, einfache LaTeX-Reste ersetzen. Nur für die Anzeige; die Antwort
    wurde mit dem Originaltext erzeugt."""
    t = re.sub(r"(?<=[a-zäöüß])-\n(?=[a-zäöüß])", "", text or "")
    for k, v in _LATEX_ERSATZ.items():
        t = t.replace(k, v)
    t = re.sub(r"\$([^$]{1,40})\$", r"\1", t)
    zeilen, gesehen = [], set()
    for z in (x.strip() for x in t.split("\n")):
        if not z:
            continue
        if len(z) < 45 and z in gesehen:      # kurze Zeile schon gezeigt (doppelte Tabelle)
            continue
        gesehen.add(z)
        zeilen.append(z)
    absaetze, aktuell = [], []
    for z in zeilen:
        if len(z) < 45:                       # Tabellenzeile / Überschrift: eigene Zeile
            if aktuell:
                absaetze.append(" ".join(aktuell))
                aktuell = []
            absaetze.append(z)
        else:
            aktuell.append(z)
    if aktuell:
        absaetze.append(" ".join(aktuell))
    return "\n".join(absaetze)


def _woerter(text):
    return {w for w in re.findall(r"[a-zäöüß]{3,}|[a-zäöüß]\d+", (text or "").lower())}


def passende_stelle(auszug, antwort):
    """Der Satz bzw. die Zeile des Auszugs, die der Antwort inhaltlich am nächsten liegt (Wortüberlappung)."""
    ziel = _woerter(antwort)
    geschuetzt = re.sub(r"\b(bzw|ca|z\. ?B|d\. ?h|u\. ?a|Abb|Tab|Nr|vgl|Gl|usw|ggf)\.", lambda m: m.group(0).replace(".", "\x00"), auszug)
    kandidaten = [s.strip().replace("\x00", ".") for z in geschuetzt.split("\n")
                  for s in re.split(r"(?<=[.!?])\s+", z) if s.strip()]
    if not ziel or not kandidaten:
        return ""
    wert = lambda s: len(_woerter(s) & ziel) / (1 + 0.1 * len(_woerter(s)))
    beste = max(kandidaten, key=wert)
    return beste if _woerter(beste) & ziel else ""


# --- Buchseite als Bild (PDF liegt lokal in daten/quellen/<buch>/) --------------------------------------------
QUELLEN_WURZEL = _os.environ.get("LERNASSISTENT_QUELLEN", "daten/quellen")


def _buch_schluessel(buch):
    wort = ((buch or "").strip().split() or [""])[0].lower()
    for a, b in (("ö", "oe"), ("ä", "ae"), ("ü", "ue"), ("ß", "ss")):
        wort = wort.replace(a, b)
    return wort


def pdf_pfad(buch):
    """Größte PDF in daten/quellen/<buch>*/ (Buchname 'Böge' -> 'boege'); None, wenn nicht vorhanden."""
    schluessel = _buch_schluessel(buch)
    if not schluessel:
        return None
    treffer = glob.glob(f"{QUELLEN_WURZEL}/{schluessel}*/*.pdf") + glob.glob(f"{QUELLEN_WURZEL}/{schluessel}*.pdf")
    return max(treffer, key=lambda f: _os.path.getsize(f)) if treffer else None


def _norm_woerter(text):
    t = re.sub(r"-\s*\n\s*", "", text or "").lower()
    return re.sub(r"[^a-zäöüß0-9]+", " ", t).split()


def _schindeln(woerter, n=4):
    return {tuple(woerter[i:i + n]) for i in range(max(0, len(woerter) - n + 1))}


if fitz is not None:
    @st.cache_resource(show_spinner=False)
    def _pdf_offen(pfad):
        return fitz.open(pfad)

    @st.cache_data(show_spinner=False, max_entries=256)
    def finde_pdf_seite(pfad, seite, text):
        """Index (0-basiert) der PDF-Seite, die den Chunk-Text enthält. Die Seitenzahl des Chunks kann
        gedruckte Seitenzahl oder PDF-Seite sein; deshalb wird um sie herum gesucht (Wortfolgen-Vergleich)."""
        doc = _pdf_offen(pfad)
        ziel = _schindeln(_norm_woerter(text[:900]))
        if not ziel:
            return None
        beste, bester_wert = None, 0.0
        for d in sorted(range(-90, 91), key=abs):
            p = int(seite) - 1 + d
            if 0 <= p < len(doc):
                wert = len(ziel & _schindeln(_norm_woerter(doc[p].get_text()))) / len(ziel)
                if wert >= 0.5:
                    return p
                if wert > bester_wert:
                    beste, bester_wert = p, wert
        return beste if bester_wert >= 0.2 else None

    @st.cache_data(show_spinner=False, max_entries=64)
    def seitenbild(pfad, p, stelle):
        """PNG der Buchseite; die passende Stelle wird markiert und die Seite auf deren Umgebung zugeschnitten."""
        page = _pdf_offen(pfad)[p]
        rects = []
        for q in (stelle[:70], stelle[:40], stelle[:25]):
            if q and len(q) >= 12:
                rects = page.search_for(q)
                if rects:
                    break
        clip, annots = page.rect, []
        if rects:
            y0, y1 = min(r.y0 for r in rects), max(r.y1 for r in rects)
            clip = fitz.Rect(0, max(0, y0 - 140), page.rect.width, min(page.rect.height, y1 + 200))
            annots = [page.add_highlight_annot(r) for r in rects]
        png = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), clip=clip).tobytes("png")
        for a in annots:
            page.delete_annot(a)
        return png, bool(rects)


def zeige_buchseite(buch, seite, text, stelle, key):
    """Zeigt die Buchseite zur Quelle, falls PDF und PyMuPDF vorhanden sind."""
    pfad = pdf_pfad(buch)
    if fitz is None or not pfad or not seite:
        return
    if not st.checkbox("📖 Buchseite zeigen", value=key.endswith("_1"), key=key):
        return
    try:
        p = finde_pdf_seite(pfad, int(seite), text)
        if p is None:
            st.caption("Die Buchseite konnte nicht eindeutig gefunden werden.")
            return
        png, markiert = seitenbild(pfad, p, stelle or "")
        unterschrift = f"{buch} · PDF-Seite {p + 1}" + (" · gelb = passende Stelle" if markiert else "")
        try:
            st.image(png, caption=unterschrift, width="stretch")
        except TypeError:  # ältere Streamlit-Versionen
            st.image(png, caption=unterschrift, use_container_width=True)
    except Exception as e:  # Anzeige darf die Antwort nie verhindern
        st.caption(f"Buchseite nicht verfügbar ({type(e).__name__}).")


def quellen_gruppen(eintrag):
    """Chunks je (Buch, Seite, Thema) zusammenfassen: überlappende Nachbar-Chunks wären sonst doppelt."""
    gruppen = {}
    for c in eintrag.get("top_chunks") or []:
        schluessel = (c.get("buch") or "", c.get("seite") or c.get("pdf_seite") or "", c.get("thema") or "")
        gruppen.setdefault(schluessel, []).append(c)
    return gruppen


def zeige_quellen(eintrag, idx=0):
    """Quellen je Buchseite: zur Antwort passende Stelle zuerst, bereinigter Auszug, optional die Buchseite
    als Bild mit markierter Stelle."""
    gruppen = quellen_gruppen(eintrag)
    if not gruppen:
        return
    antwort = " ".join(str(eintrag.get(k) or "") for k in ("loesung", "hinweis"))
    ziel = _woerter(antwort + " " + str(eintrag.get("frage") or ""))
    infos = []
    for (buch, seite, thema), cs in gruppen.items():
        auszug = bereinige_auszug("\n".join(c.get("text") or "" for c in cs))
        stelle = passende_stelle(auszug, antwort)
        gemeinsam = len(_woerter(stelle) & ziel) if stelle else 0
        infos.append(((buch, seite, thema), cs, auszug, stelle, gemeinsam < 3))
    infos.sort(key=lambda t: t[4])  # passende zuerst (stabil: Reihenfolge der Suche bleibt sonst erhalten)
    (b0, s0, t0), *_ = infos[0]  # erste (passendste) Quelle direkt im Kopf
    kopf = " · ".join(x for x in (b0, (t0 or "").split(">")[-1].strip(), f"S. {s0}" if s0 else "") if x)
    with st.expander(f"📎 Quellen: {kopf}" + (f"  (+{len(infos) - 1})" if len(infos) > 1 else "")):
        for i, ((buch, seite, thema), cs, auszug, stelle, schwach) in enumerate(infos, start=1):
            thema_kurz = thema.split(">")[-1].strip() if thema else ""
            st.markdown(f"**Quelle {i}:** " + (f"{buch} · " if buch else "") + thema_kurz
                        + (f" · S. {seite}" if seite else "")
                        + (" &nbsp; <span style='opacity:.6'>· weniger relevant für diese Antwort</span>" if schwach else ""),
                        unsafe_allow_html=True)
            if schwach and not st.checkbox("Trotzdem anzeigen", key=f"schwach_{idx}_{i}"):
                continue
            if stelle:
                st.markdown(f"> **Passende Stelle:** {stelle}")
            zeige_buchseite(buch, seite, cs[0].get("text") or "", stelle, key=f"bild_{idx}_{i}")
            # Expander dürfen nicht verschachtelt werden -> Schalter
            lang = len(auszug) > 600
            if not (stelle or lang) or st.checkbox("Ganzen Textauszug zeigen", key=f"auszug_{idx}_{i}"):
                st.text(auszug[:1500] + (" …" if len(auszug) > 1500 else ""))


# --- Vertrauens-Hinweise, Sicherheitshinweis, Schrittleiste ---------------------------------------------------
def vertrauens_zeile(eintrag, bildfrage=False, thema_fehlt=False):
    """Kurze, nachvollziehbare Hinweise aus Prüfungen, die ohnehin laufen (kein zusammengesetzter Zahlenwert):
    Status der Antwort, ob eine zur Antwort passende Textstelle gefunden wurde, Ergebnis der Rechenprüfung."""
    status = eintrag.get("status")
    chips = []
    if status == "TEILWEISE":
        chips.append("◐ nur teilweise im Lernmaterial")
    elif status == "BEANTWORTET":
        chips.append("📖 Antwort stützt sich auf das Lernmaterial")  # neutral, kein Richtigkeitsversprechen
    antwort = " ".join(str(eintrag.get(k) or "") for k in ("loesung", "hinweis"))
    gruppen = quellen_gruppen(eintrag)
    gefunden = any(passende_stelle(bereinige_auszug("\n".join(c.get("text") or "" for c in cs)), antwort)
                   for cs in gruppen.values())
    chips.append("📖 Passende Buchstelle gefunden" if gefunden else "◔ keine eindeutig passende Textstelle – bitte prüfen")
    if bildfrage:
        if thema_fehlt:  # ohne Thema in der Eingabe sind die grünen Marken nicht belastbar
            chips = [c for c in chips if not c.startswith(("✓", "📖"))]
        chips.insert(0, "◔ beruht auf automatisch beschriebener Abbildung – bitte mit dem Buch vergleichen")
    rp = eintrag.get("rechen_pruefung") or ""
    if rp == "nachgebessert":
        chips.append("✓ Rechnung nachgerechnet und korrigiert")
    elif rp == "markiert":
        chips.append("⚠ Rechnung bitte prüfen")
    elif rp == "ersetzt":
        chips.append("⚠ Antwort durch Nachrechnung ersetzt")
    elif rp == "abweichung_ungestuetzt":
        chips.append("◔ unabhängige Nachrechnung weicht ab (Formel nicht im Lernmaterial belegt) – bitte prüfen")
    elif rp == "ungeprueft":
        chips.append("◔ Rechnung konnte nicht nachgeprüft werden – bitte selbst nachrechnen")
    elif rp == "denkmodus":
        chips.append("◔ im Denkmodus neu gerechnet (Rechenschritte nachgerechnet) – bitte mit dem Buch prüfen")
    elif rp == "kopf_korrigiert":
        chips.append("✓ Ergebnis im ersten Satz an die eigene Rechnung angeglichen")
    elif re.match(r"RB-v[1234] Ergebnis", str(eintrag.get("rechen_befund") or "")):
        chips.append("✓ Rechnung nachgerechnet")
    if re.search(r"Formel (nicht im Material|ohne Quelle)", str(eintrag.get("rechen_befund") or "")):
        chips.append("◔ Formel nicht im Lernmaterial gefunden – bitte prüfen")
    return chips


_SICHERHEIT = re.compile(r"stromschlag|lebensgefahr|berührungsspannung|schutzleiter|schutzmaßnahme|herzkammerflimmern|"
                         r"freischalten|spannungsfrei|not-?aus|not-?halt|zweihand|offener sekundär|hochspannung|"
                         r"druckluft|absturz|quetsch", re.I)


def zeige_vertrauen(eintrag, bildfrage=False, thema_fehlt=False):
    """Vertrauens-Hinweise als farbige Marken (grün = geprüft, orange = bitte selbst prüfen)."""
    teile = []
    for c in vertrauens_zeile(eintrag, bildfrage, thema_fehlt):
        ok = c.startswith(("✓", "📖"))
        farbe = "140,140,140" if ok else "224,140,0"  # neutral grau statt grün; orange = bitte prüfen
        teile.append(f"<span style='display:inline-block;margin:2px 6px 2px 0;padding:2px 10px;border-radius:12px;"
                     f"font-size:.82rem;background:rgba({farbe},.16);border:1px solid rgba({farbe},.55)'>{c}</span>")
    st.markdown("".join(teile), unsafe_allow_html=True)
    st.caption("Wichtige Angaben bitte mit der Buchseite vergleichen.")
    if bildfrage and thema_fehlt:
        st.caption("Tipp: Nenne in deiner Frage das Thema (z. B. „erkläre diese Abbildung der Gleichstrommaschine“) – dann sucht der Assistent im passenden Kapitel.")


def sicherheits_thema(frage, loesung):
    """Regelbasiert: Begriffe, die auf Gefährdung hindeuten (bewusst eng, damit „Strom“ oder „230 V“ allein nicht auslösen)."""
    return bool(_SICHERHEIT.search(f"{frage} {loesung}"))


def schrittleiste(stufe, hat_idee):
    """Lernschritte Hinweis → Dein Versuch → Rückmeldung → Lösung; aktueller Schritt hervorgehoben."""
    namen = ["Hinweis", "Dein Versuch", "Rückmeldung", "Lösung"]
    if stufe >= 2:
        zustand = ["fertig", "fertig" if hat_idee else "aus", "fertig" if hat_idee else "aus", "aktiv"]
    elif hat_idee:
        zustand = ["fertig", "fertig", "aktiv", "offen"]  # Rückmeldung erhalten; weiterer Versuch oder Lösung
    else:
        zustand = ["fertig", "aktiv", "offen", "offen"]
    stil = {"fertig": ("✓", "rgba(140,140,140,.18)", "rgba(140,140,140,.5)", "1"),
            "aktiv": ("●", "rgba(255,153,0,.22)", "rgba(255,153,0,.9)", "1"),
            "offen": ("○", "transparent", "rgba(140,140,140,.4)", ".6"),
            "aus": ("–", "transparent", "rgba(140,140,140,.3)", ".45")}
    teile = []
    for i, (n, z) in enumerate(zip(namen, zustand), start=1):
        sym, bg, rand, op = stil[z]
        fett = "font-weight:600;" if z == "aktiv" else ""
        teile.append(f"<span style='display:inline-block;margin:2px 4px 2px 0;padding:2px 10px;border-radius:12px;"
                     f"font-size:.8rem;background:{bg};border:1px solid {rand};opacity:{op};{fett}'>{sym} {i} {n}</span>")
    st.markdown("".join(teile), unsafe_allow_html=True)


URTEIL_SYMBOL = {"richtig": "✅", "teilweise": "🟡", "falsch": "🔁", "keine_idee": "💬"}


def zeige_ideen(versuche, stufe):
    """Ideen + Rückmeldungen, die auf dieser Stufe abgegeben wurden (chronologisch
    an der Stelle, an der sie entstanden sind)."""
    for v in versuche:
        if v["stufe"] == stufe:
            st.markdown(f"💭 **Deine Idee:** {v['idee']}")
            st.markdown(f"{URTEIL_SYMBOL.get(v['urteil'], '💬')} **Rückmeldung:** {v['rueckmeldung']}")


def ideen_eingabe(idx, eintrag, versuche, aktuelle_stufe):
    """Optionales Feld "Deine Idee?". Der Key
    enthält die Versuchsnummer, damit das Feld nach dem Absenden leer ist."""
    n = len(versuche)
    text = st.text_area(
        "💭 Deine Idee? (optional) — Was glaubst du, wie die Antwort lautet?",
        key=f"idee_text_{idx}_{n}", height=80,
        placeholder="Schreib deine Vermutung in eigenen Worten …",
    )
    if st.button("Idee prüfen lassen", key=f"btn_idee_{idx}_{n}", type="primary"):  # Hauptaktion
        idee = text.strip()
        if not idee:
            st.warning("Schreib zuerst deine Idee in das Feld.")
            return
        with st.spinner("Der Assistent schaut sich deine Idee an …"):
            fb = gib_feedback(eintrag, idee)
        versuche.append({"idee": idee, "urteil": fb["urteil"],
                         "rueckmeldung": fb["rueckmeldung"], "stufe": aktuelle_stufe})
        protokolliere_idee(st.session_state["sitzungs_id"], idx + 1, eintrag,
                           versuch_nr=n + 1, stufe=aktuelle_stufe, fb=fb)
        st.rerun()


def zeige_eintrag(idx, eintrag, ist_letzter):
    """Zeigt einen Frage-Antwort-Eintrag mit stufenweiser Freischaltung
    (Hinweis -> [Deine Idee? + Rückmeldung] -> Lösung). Stufe 1 = Hinweis,
    Stufe 2 = Lösung geöffnet. Der Fortschritt pro Eintrag wird in
    st.session_state['stufe_' + idx] gehalten, die Ideen in 'ideen_' + idx.
    Das Ideen-Feld erscheint nur bei der jüngsten Frage, solange die Lösung noch
    nicht geöffnet ist (höchstens MAX_VERSUCHE Ideen pro Frage)."""
    stufe_key = f"stufe_{idx}"
    if stufe_key not in st.session_state:
        st.session_state[stufe_key] = 1
    ideen_key = f"ideen_{idx}"
    if ideen_key not in st.session_state:
        st.session_state[ideen_key] = []
    versuche = st.session_state[ideen_key]

    with st.chat_message("user"):
        if st.session_state.get("bilder", {}).get(idx):
            st.image(st.session_state["bilder"][idx], width=320)
        st.write(eintrag["frage"])

    with st.chat_message("assistant"):
        if eintrag.get("_v21_job") is not None:  # Hinweis-zuerst-Modus: Hinweis steht, Lösung wird noch vorbereitet
            _v21_wartend(idx, eintrag, ist_letzter)
            return
        verweigert = eintrag.get("status") in ("GATE", "NICHT_IM_MATERIAL")
        if verweigert:
            # Keine Treffer im Lernmaterial: ehrliche Rückmeldung statt Stufen und Quellen
            st.info(f"🔎 {eintrag['loesung']}")
            st.caption("Du kannst die Frage anders formulieren, unter „Verfügbare Themen“ nachsehen "
                       "oder deine Lehrkraft fragen.")
        elif not eintrag["vollstaendig_geparst"]:
            # Fallback: Modell hat das Stufen-Format nicht eingehalten,
            # volle Antwort direkt zeigen statt mit leeren Stufen zu verwirren.
            zeige_loesung(eintrag["loesung"], {"markiert": True, "ersetzt": "ersetzt", "denkmodus": "denkmodus", "ungeprueft": "ungeprueft"}.get(eintrag.get("rechen_pruefung"), False))
        else:
            aktuelle_stufe = 2 if st.session_state.get("loesung_direkt") else st.session_state[stufe_key]
            schrittleiste(aktuelle_stufe, bool(versuche))
            st.markdown(f"💡 **Hinweis:** {eintrag['hinweis']}")
            zeige_ideen(versuche, 1)

            if aktuelle_stufe >= 2:
                _mk = {"markiert": True, "ersetzt": "ersetzt", "denkmodus": "denkmodus", "ungeprueft": "ungeprueft"}.get(eintrag.get("rechen_pruefung"), False)
                _ue = st.session_state.get(f"uebung_{idx}") or {}
                if _ue.get("u") and not _ue.get("fb"):  # während der Übungsfrage eingeklappt
                    with st.expander("✅ Lösung (eingeklappt, solange du die Übungsfrage beantwortest)"):
                        zeige_loesung(eintrag["loesung"], _mk)
                else:
                    zeige_loesung(eintrag["loesung"], _mk)

            if (ist_letzter and aktuelle_stufe < 2 and len(versuche) < MAX_VERSUCHE
                    and idee_moeglich(eintrag)):
                ideen_eingabe(idx, eintrag, versuche, aktuelle_stufe)

            if aktuelle_stufe == 1:
                if st.button("✅ Lösung anzeigen", key=f"btn_loesung_{idx}"):
                    st.session_state[stufe_key] = 2
                    protokolliere_interaktion(st.session_state["sitzungs_id"], eintrag, scaffolding_stufe_erreicht=2)
                    st.rerun()

        loesung_offen = st.session_state[stufe_key] >= 2 or st.session_state.get("loesung_direkt")
        if eintrag["quellen"] and not verweigert and (not eintrag["vollstaendig_geparst"] or loesung_offen):
            zeige_vertrauen(eintrag, bildfrage=idx in st.session_state.get("bilder", {}),
                            thema_fehlt=st.session_state.get("bild_meta", {}).get(idx, {}).get("thema_fehlt", False))
            zeige_quellen(eintrag, idx)
        zeige_zeiten(eintrag)
        if not verweigert and (eintrag["sicherheitshinweis"] or sicherheits_thema(eintrag["frage"], eintrag.get("loesung", ""))):
            st.warning(
                "⚠️ Dieses Thema ist sicherheitsrelevant. Setze nichts davon allein an spannungsführenden "
                "oder bewegten Anlagen um und besprich das Vorgehen vorher mit deiner Ausbilderin oder deinem Ausbilder."
            )
        if ist_letzter and not verweigert and loesung_offen and eintrag.get("vollstaendig_geparst") \
                and eintrag.get("status") in ("BEANTWORTET", "TEILWEISE") and eintrag.get("top_chunks"):
            zeige_lernhilfen(idx, eintrag)


def zeige_lernhilfen(idx, eintrag):
    """Anschlussfragen (Knöpfe) und eine Übungsfrage; beides nur aus dem verwendeten Lernmaterial."""
    sid = st.session_state["sitzungs_id"]
    st.divider()
    # --- Anschlussfragen
    fk = f"folge_{idx}"
    if fk not in st.session_state:
        if st.button("💬 Wie kann ich weiterlernen?", key=f"btn_folge_{idx}"):
            with st.spinner("Suche passende Anschlussfragen …"):
                t0 = time.perf_counter()
                st.session_state[fk] = lernhilfen.folgefragen(eintrag)
            lernhilfen.protokolliere(sid, idx + 1, "folgefragen_vorgeschlagen",
                                     text=" | ".join(st.session_state[fk]), sekunden=round(time.perf_counter() - t0, 1))
            st.rerun()
    else:
        if st.session_state[fk]:
            st.caption("Anschlussfragen (nur aus dem Lernmaterial beantwortbar):")
            for j, q in enumerate(st.session_state[fk]):
                if st.button(q, key=f"btn_folge_{idx}_{j}", width="stretch"):
                    lernhilfen.protokolliere(sid, idx + 1, "folgefrage_gewaehlt", text=q)
                    st.session_state["naechste_frage"] = q
                    st.rerun()
        else:
            st.caption("Dazu habe ich keine passende Anschlussfrage im Lernmaterial gefunden.")
    # --- Übungsfrage (keine Rechenaufgaben)
    if lernhilfen.ist_numerisch(eintrag):
        return
    uk = f"uebung_{idx}"
    if uk not in st.session_state:
        if st.button("🧪 Teste dich selbst", key=f"btn_uebung_{idx}"):
            with st.spinner("Erstelle eine Übungsfrage …"):
                t0 = time.perf_counter()
                st.session_state[uk] = {"u": lernhilfen.uebungsfrage(eintrag), "fb": None, "zeige": False}
            u = st.session_state[uk]["u"]
            lernhilfen.protokolliere(sid, idx + 1, "uebung_gestellt" if u else "uebung_verworfen",
                                     text=(u or {}).get("frage", ""), sekunden=round(time.perf_counter() - t0, 1))
            st.rerun()
        return
    z = st.session_state[uk]
    if not z["u"]:
        st.caption("Dazu ließ sich keine gut belegte Übungsfrage erstellen.")
        return
    st.markdown(f"🧪 **Übungsfrage:** {z['u']['frage']}")
    if z["fb"]:
        st.markdown(f"💭 **Deine Antwort:** {z['fb']['idee']}")
        st.markdown(f"{URTEIL_SYMBOL.get(z['fb']['urteil'], '💬')} **Rückmeldung:** {z['fb']['rueckmeldung']}")
        if z["zeige"]:
            st.markdown(f"✅ **Musterantwort:** {z['u']['loesung']}")
        elif st.button("Musterantwort zeigen", key=f"btn_muster_{idx}"):
            z["zeige"] = True
            lernhilfen.protokolliere(sid, idx + 1, "uebung_musterantwort", text=z["u"]["frage"])
            st.rerun()
        return
    antwort = st.text_area("Deine Antwort:", key=f"uebung_text_{idx}", height=80)
    if st.button("Antwort prüfen lassen", key=f"btn_uebung_pruef_{idx}"):
        if not antwort.strip():
            st.warning("Schreib zuerst deine Antwort in das Feld.")
            return
        with st.spinner("Der Assistent schaut sich deine Antwort an …"):
            fb = lernhilfen.uebung_bewerten(z["u"], antwort.strip(), eintrag["top_chunks"])
        z["fb"] = fb
        lernhilfen.protokolliere(sid, idx + 1, "uebung_antwort", text=z["u"]["frage"], antwort=antwort.strip(),
                                 urteil=fb["urteil"], sekunden=fb.get("sekunden", ""))
        st.rerun()


def zeige_dashboard():
    """Nutzungsauswertung aus den Protokollen (nur im Entwicklermodus: LERNASSISTENT_DEV=1 oder ?dev=1)."""
    st.subheader("📊 Nutzungsauswertung")
    nur = st.toggle("Nur diese Sitzung", value=True)
    a = lernhilfen.auswertung(st.session_state["sitzungs_id"] if nur else None)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sitzungen", a["sitzungen"])
    c2.metric("Fragen", a["fragen"])
    c3.metric("Lösung geöffnet", f"{a['loesung_geoeffnet']} / {a['fragen']}")
    c4.metric("Ideen abgegeben", a["ideen"])
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Antwort-Status (je Frage)")
        if a["status"]:
            st.bar_chart(a["status"])
    with col2:
        st.caption("Urteile über Ideen")
        if a["urteile"]:
            st.bar_chart(a["urteile"])
    if a.get("hinweis", {}).get("fragen"):
        st.markdown("**Umgang mit dem Hinweis**")
        zeige_hinweis_nutzung(a["hinweis"])
    if a["hilfen"]:
        st.caption("Lernhilfen: " + " · ".join(f"{k}: {v}" for k, v in a["hilfen"].items()))
    if a["tabelle"]:
        st.dataframe(a["tabelle"], width="stretch", hide_index=True)
    if not nur and a["ohne_demo"] != a["fragen"]:
        st.caption("Hinweis: Sitzungen mit TEST-Präfix sind Demo-Sitzungen.")


def zeige_ueber():
    """Technische Eckdaten und Datenschutz auf einen Blick."""
    from collections import Counter
    buecher = Counter(c.get("buch") or "Lernmaterial" for c in CHUNKS)
    try:
        import reranker as _rr
        reranker_name = getattr(_rr, "RERANKER_MODELL", None) or getattr(_rr, "MODELL", None) or "Cross-Encoder"
    except Exception:
        reranker_name = "Cross-Encoder"
    with st.expander("🔒 Über diesen Assistenten"):
        st.markdown(
            "**Lernmaterial:** " + ", ".join(f"{b} ({n:,} Textabschnitte)".replace(",", ".") for b, n in buecher.items())
            + "\n\n**Sprachmodell:** " + _rp.MODEL_NAME + " (läuft lokal)  \n"
            f"**Suche:** Stichwort- + Bedeutungssuche, Begriffsgraph, Neu-Ordnung mit {reranker_name}  \n"
            f"**Version:** Antwort-Prompt {_rp.SCAFFOLDING_VERSION}, Rechenprüfung {'RP-v13' if getattr(_rp, 'RP_V13', False) else _rp.RECHEN_PRUEFUNG_VERSION}\n\n"
            "**Datenschutz:** Alles läuft auf diesem Rechner. Es werden keine Daten an Cloud-Dienste gesendet. "
            "Gespeichert werden Sitzungs-ID, Fragen, Antworten, deine Ideen und der Fragebogen, "
            "ohne Namen."
        )


# Beispiele auf der leeren Startseite (abschalten: LERNASSISTENT_BEISPIELE=0)
BEISPIELE = [
    "Warum nimmt man für Spulen im kHz-Bereich keine geblechten Eisenkerne mehr?",
    "Auf dem Leistungsschild eines Verteiltransformators steht die Schaltgruppe Yzn 5. Was bedeuten die Buchstaben und die Kennzahl?",
    "Wie heißt die Fläche am Schneidkeil, über die der Span abläuft?",
    "Zwei Rohre (d = 40 mm) werden durch eine Überlappungsklebung verbunden und mit dem Torsionsmoment MT = 50 Nm belastet. "
    "Die Bindefestigkeit des Klebstoffs beträgt KB = 20 N/mm², die Sicherheit bei wechselnder Beanspruchung S = 4. "
    "Welche Überlappungslänge b ist mindestens erforderlich?",
]


def _ist_dev():
    return _os.environ.get("LERNASSISTENT_DEV") == "1" or st.query_params.get("dev") == "1"


def _symbol(e):
    """Symbol im Verlauf: abgelehnt, teilweise, Rechnung, sonst Frage."""
    if e.get("status") in ("GATE", "NICHT_IM_MATERIAL"):
        return "🔎"
    if e.get("status") == "TEILWEISE":
        return "◐"
    if e.get("rechen_pruefung"):
        return "🧮"
    return "💬"


def _kurz(text, n=38):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def zeige_hinweis_nutzung(h, kompakt=False):
    """Kennzahlen zum Umgang mit dem Hinweis (Seitenleiste kompakt, Auswertung ausführlich)."""
    n = h["fragen"]
    if kompakt:
        st.markdown(
            f"<div style='font-size:.85rem;line-height:1.7'>✍️ Selbst versucht: <b>{h['versucht']}/{n}</b><br>"
            f"🎯 Mit Hinweis gelöst: <b>{h['geloest']}/{n}</b><br>"
            f"⏭ Direkt zur Lösung: <b>{h['direkt']}/{n}</b></div>", unsafe_allow_html=True)
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selbst versucht", f"{h['versucht']}/{n}", help="Fragen mit mindestens einer Idee, bevor die Lösung geöffnet wurde")
    c2.metric("Mit Hinweis gelöst", f"{h['geloest']}/{n}", help="Eine Idee wurde vor dem Öffnen der Lösung als richtig beurteilt")
    c3.metric("Nach Rückmeldung besser", f"{h['verbessert']}/{h['mehrere']}",
              help="Unter Fragen mit mehreren Ideen: eine spätere Idee wurde besser beurteilt als die vorherige")
    c4.metric("Direkt zur Lösung", f"{h['direkt']}/{n}", help="Lösung geöffnet, ohne vorher eine Idee aufzuschreiben")
    if h["versucht"]:
        st.caption(f"Urteil über den ersten Versuch (Ø {h['versuche_mittel']} Ideen je Frage vor der Lösung)")
        st.bar_chart(h["erster"])


def seitenleiste():
    """Seitenleiste wie in Chat-Anwendungen – Verlauf (neueste oben, mit Zeit), Sitzungsübersicht, Infos."""
    verlauf = st.session_state["verlauf"]
    fokus = st.session_state.get("fokus")
    with st.sidebar:
        st.markdown(f"### 🎓 {APP_NAME}")
        st.caption(f"Sitzung: {st.session_state['sitzungs_id']}")
        c1, c2 = st.columns(2)
        if c1.button("📋 Alle Fragen", width="stretch", disabled=fokus is None):
            st.session_state["fokus"] = None
            st.rerun()
        if c2.button("🗑 Neu starten", width="stretch", disabled=not verlauf,
                     help="Leert den Verlauf auf dem Bildschirm (das Protokoll bleibt erhalten)."):
            for k in [k for k in st.session_state if k.startswith(("stufe_", "ideen_", "idee_text_", "folge_", "uebung_"))]:
                del st.session_state[k]
            st.session_state["verlauf"] = []
            st.session_state["bilder"], st.session_state["bild_meta"] = {}, {}
            st.session_state["fokus"] = None
            st.rerun()

        st.markdown("**Verlauf**")
        if not verlauf:
            st.caption("Noch keine Fragen.")
        for i in range(len(verlauf) - 1, -1, -1):
            e = verlauf[i]
            t = sum((e.get("zeiten") or {}).values())
            if st.button(f"{_symbol(e)} {_kurz(e.get('frage'))}" + (f" · {sek(t)}" if t else ""), key=f"verlauf_{i}",
                         width="stretch", type="primary" if fokus == i else "secondary", help=str(e.get("frage") or "")):
                st.session_state["fokus"] = i
                st.rerun()

        if verlauf:
            st.markdown("**Diese Sitzung**")
            zeiten = [sum((e.get("zeiten") or {}).values()) for e in verlauf if e.get("zeiten")]
            im_buch = sum(e.get("status") in ("BEANTWORTET", "TEILWEISE") for e in verlauf)
            geoeffnet = sum(st.session_state.get(f"stufe_{i}", 1) >= 2 for i in range(len(verlauf)))
            ideen = sum(len(st.session_state.get(f"ideen_{i}", [])) for i in range(len(verlauf)))
            m1, m2 = st.columns(2)
            m1.metric("Fragen", len(verlauf))
            m2.metric("Ø Zeit", sek(sum(zeiten) / len(zeiten)) if zeiten else "–")
            m3, m4 = st.columns(2)
            m3.metric("Im Buch belegt", f"{im_buch}/{len(verlauf)}")
            m4.metric("Eigene Ideen", ideen)
            st.caption(f"Lösung geöffnet: {geoeffnet}/{len(verlauf)} · abgelehnt (nicht im Buch): {len(verlauf) - im_buch}")
            h = lernhilfen.hinweis_nutzung([
                (st.session_state.get(f"stufe_{i}", 1) >= 2,
                 [(x.get("stufe"), x.get("urteil")) for x in st.session_state.get(f"ideen_{i}", [])])
                for i, e in enumerate(verlauf) if e.get("status") in ("BEANTWORTET", "TEILWEISE")])
            if h["fragen"]:
                st.markdown("**Umgang mit dem Hinweis**")
                zeige_hinweis_nutzung(h, kompakt=True)

        st.divider()
        st.checkbox("Lösung sofort anzeigen (Demo)", key="loesung_direkt",
                    help="Zeigt Hinweis und Lösung gleichzeitig. Aus = Hinweis zuerst, Lösung auf Klick (Studienablauf).")
        with st.expander("📚 Verfügbare Themen"):
            themen = sorted(set(c["thema"] for c in CHUNKS))
            st.write(", ".join(themen))
        with st.expander("ℹ️ Wie funktioniert die Antwort?"):
            st.write(
                "Du bekommst zuerst nur einen **Hinweis** — versuch, damit selbst "
                "weiterzukommen. Wenn du magst, schreib **deine Idee** auf: Der Assistent "
                "sagt dir, was daran schon stimmt und worüber du noch nachdenken kannst, "
                "ohne die Lösung zu verraten. Du kannst bis zu drei Ideen ausprobieren. "
                "Wenn du nicht weiterkommst, zeig dir die **Lösung mit Begründung** an."
            )
        zeige_ueber()
        if _ist_dev():
            with st.expander("📊 Nutzungsauswertung (Entwicklermodus)"):
                zeige_dashboard()


def willkommen():
    """leere Startseite mit kurzer Erklärung und anklickbaren Beispielfragen."""
    st.markdown("Stell eine Frage zur **Elektrotechnik** oder zum **Maschinenbau**. Du bekommst zuerst einen "
                "**Hinweis** und kannst selbst eine Idee aufschreiben; die **Lösung** mit den Buchstellen gibt es auf Klick.")
    if _os.environ.get("LERNASSISTENT_BEISPIELE", "1") == "0":
        return
    st.caption("Zum Ausprobieren:")
    spalten = st.columns(2)
    for j, q in enumerate(BEISPIELE):
        if spalten[j % 2].button(q, key=f"bsp_{j}", width="stretch"):
            st.session_state["naechste_frage"] = q
            st.rerun()


_V21_HZ = _os.environ.get("LERNASSISTENT_HINWEIS_ZUERST") == "1"  # optional: Hinweis vor der fertigen Prüfung zeigen


def _v21_job_starten(frage):
    """Hinweis-zuerst-Modus: beantwortet die Frage in einem Hintergrund-Thread (vollständige V20-Pipeline). Der Thread schreibt nur
    in das dict job (keine Streamlit-Aufrufe); die Oberfläche liest es."""
    import threading
    job = {"vorab": None, "ergebnis": None, "fehler": None, "phasen": {}, "quellen": None, "start": time.perf_counter()}

    def rueckruf(phase, ereignis, dauer=None, daten=None):
        if ereignis == "hinweis_vorab":
            if (daten or {}).get("status") in ("BEANTWORTET", "TEILWEISE") and (daten or {}).get("hinweis"):
                job["vorab"] = daten
        elif ereignis == "quellen":
            job["quellen"] = daten
        elif ereignis in ("start", "ende"):
            job["phasen"][phase] = (ereignis, dauer)
    rueckruf._v21 = True

    def arbeit():
        try:
            job["ergebnis"] = beantworte_frage(frage, CHUNKS, fortschritt=rueckruf)
        except Exception as fehler:
            print(f"FEHLER beantworte_frage (V21-S): {type(fehler).__name__}: {fehler}")
            job["fehler"] = fehler
    threading.Thread(target=arbeit, daemon=True).start()
    return job


def _v21_status_zeigen(status, job, zeilen):
    """Hinweis-zuerst-Modus: Fortschritt wie fortschritt_anzeige, aber aus dem Job gelesen."""
    if job["quellen"] and "quellen" not in zeilen:
        orte = []
        for c in job["quellen"]:
            ort = (f"{c['buch']} " if c.get("buch") else "") + (f"S. {c['seite']}" if c.get("seite") else "")
            if ort.strip() and ort.strip() not in orte:
                orte.append(ort.strip())
        zeilen["quellen"] = status.empty()
        if orte:
            zeilen["quellen"].markdown("📎 Gefunden: " + " · ".join(orte))
    for phase in PHASEN:
        if phase in job["phasen"]:
            ereignis, dauer = job["phasen"][phase]
            if phase not in zeilen:
                zeilen[phase] = status.empty()
            zeilen[phase].markdown(f"⏳ {PHASEN[phase][0]} …" if ereignis == "start"
                                   else f"✓ {PHASEN[phase][1]} · {sek(dauer)}")


def _v21_fertig(job, frage):
    """Hinweis-zuerst-Modus: Endergebnis (wie V20) oder Fehlerhinweis; Protokoll wie in V20 nach der Antwort."""
    if job["ergebnis"] is not None:
        erg = job["ergebnis"]
        vorab = (job.get("vorab") or {}).get("hinweis")
        if vorab and vorab != erg.get("hinweis"):
            print(f"HINWEIS V21-S: Vorab-Hinweis wich vom endgültigen ab ({frage[:60]})")
        protokolliere_interaktion(st.session_state["sitzungs_id"], erg, scaffolding_stufe_erreicht=1)
        return erg
    return {"frage": frage, "status": "GATE", "hinweis": "", "erklaerung": "", "vollstaendig_geparst": False,
            "loesung": "Die Antwort konnte gerade nicht fertig erzeugt werden. Bitte stelle die Frage noch einmal.",
            "quellen": [], "top_chunks": [], "sicherheitshinweis": None, "zeiten": {}}


def _v21_abschliessen(verlauf):
    """Hinweis-zuerst-Modus: fertige Hintergrund-Jobs durch ihr Endergebnis ersetzen."""
    for i, e in enumerate(verlauf):
        job = e.get("_v21_job")
        if job is not None and (job["ergebnis"] is not None or job["fehler"] is not None):
            verlauf[i] = _v21_fertig(job, e["frage"])


def _frage_hintergrund(frage):
    """Hinweis-zuerst-Modus: Frage starten, auf den Hinweis warten (Fortschritt sichtbar), Lösung im Hintergrund weiterrechnen."""
    with st.chat_message("user"):
        st.write(frage)
    with st.chat_message("assistant"):
        with st.status("Der Assistent arbeitet …", expanded=True) as status:
            job, zeilen = _v21_job_starten(frage), {}
            while job["ergebnis"] is None and job["fehler"] is None and job["vorab"] is None:
                _v21_status_zeigen(status, job, zeilen)
                time.sleep(0.3)
            _v21_status_zeigen(status, job, zeilen)
            if job["fehler"] is not None:
                status.update(label="Keine Antwort erzeugt", state="error", expanded=False)
                st.error("Die Antwort konnte gerade nicht erzeugt werden (das Sprachmodell hat nicht rechtzeitig "
                         "geantwortet). Bitte stelle die Frage noch einmal.")
                st.stop()
            status.update(label=f"{'Fertig' if job['ergebnis'] is not None else 'Hinweis bereit'} · "
                                f"{sek(time.perf_counter() - job['start'])}", state="complete", expanded=False)
    if job["ergebnis"] is not None:
        st.session_state["verlauf"].append(_v21_fertig(job, frage))
    else:
        v = job["vorab"]
        st.session_state["verlauf"].append({
            "frage": frage, "_v21_job": job, "hinweis": v.get("hinweis", ""), "status": v.get("status", ""),
            "vollstaendig_geparst": True, "loesung": "", "quellen": [], "top_chunks": [], "sicherheitshinweis": None,
            "zeiten": {}})
    st.session_state["fokus"] = None
    st.rerun()


def _v21_warte_auf(job, idx, eintrag):
    """Hinweis-zuerst-Modus: auf das Endergebnis warten, Eintrag ersetzen (Protokoll wie V20) und es zurückgeben."""
    while job["ergebnis"] is None and job["fehler"] is None:
        time.sleep(0.4)
    erg = _v21_fertig(job, eintrag["frage"])
    st.session_state["verlauf"][idx] = erg
    return erg


def _v21_wartend(idx, eintrag, ist_letzter=True):
    """Hinweis-zuerst-Modus: Hinweis steht; Lösung/Prüfung laufen noch. Bei der jüngsten Frage sind Ideenfeld und Lösungsknopf schon
    da (sie warten bei Bedarf kurz auf das Endergebnis); ältere wartende Einträge aktualisieren sich selbst."""
    schrittleiste(1, False)
    st.markdown(f"💡 **Hinweis:** {eintrag['hinweis']}")
    job = eintrag["_v21_job"]
    if ist_letzter:
        text = st.text_area("💭 Deine Idee? (optional) — Was glaubst du, wie die Antwort lautet?",
                            key=f"idee_text_{idx}_0", height=80, placeholder="Schreib deine Vermutung in eigenen Worten …")
        if st.button("Idee prüfen lassen", key=f"btn_idee_{idx}_0", type="primary"):
            idee = (text or "").strip()
            if not idee:
                st.warning("Schreib zuerst deine Idee in das Feld.")
            else:
                with st.spinner("Die Lösung wird noch geprüft – gleich schaut sich der Assistent deine Idee an …"):
                    erg = _v21_warte_auf(job, idx, eintrag)
                    if job["ergebnis"] is not None and erg.get("vollstaendig_geparst") and idee_moeglich(erg):
                        fb = gib_feedback(erg, idee)
                        versuche = st.session_state[f"ideen_{idx}"]
                        versuche.append({"idee": idee, "urteil": fb["urteil"], "rueckmeldung": fb["rueckmeldung"], "stufe": 1})
                        protokolliere_idee(st.session_state["sitzungs_id"], idx + 1, erg, versuch_nr=len(versuche),
                                           stufe=1, fb=fb)
                st.rerun()
        if st.button("✅ Lösung anzeigen", key=f"btn_loesung_{idx}"):
            with st.spinner("Die Lösung wird noch geprüft …"):
                erg = _v21_warte_auf(job, idx, eintrag)
            if job["ergebnis"] is not None:
                st.session_state[f"stufe_{idx}"] = 2
                protokolliere_interaktion(st.session_state["sitzungs_id"], erg, scaffolding_stufe_erreicht=2)
            st.rerun()
        st.caption("⏳ Die Lösung wird im Hintergrund noch geprüft – du kannst schon deine Idee aufschreiben.")
        return
    st.caption("⏳ Lösung und Rückmeldung werden noch vorbereitet …")

    @st.fragment(run_every=2)
    def _warte():
        if job["ergebnis"] is not None or job["fehler"] is not None:
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
    _warte()


def seite_chat():
    seitenleiste()
    st.title(f"🎓 {APP_NAME}")
    _v21_abschliessen(st.session_state["verlauf"])
    verlauf = st.session_state["verlauf"]
    anzahl = len(verlauf)
    fokus = st.session_state.get("fokus")
    if fokus is not None and not (0 <= fokus < anzahl):
        fokus = st.session_state["fokus"] = None
    if not verlauf:
        willkommen()
    if fokus is None:
        for idx, eintrag in enumerate(verlauf):
            zeige_eintrag(idx, eintrag, ist_letzter=(idx == anzahl - 1))
    else:
        st.caption(f"Frage {fokus + 1} von {anzahl} (aus dem Verlauf) · „📋 Alle Fragen“ zeigt wieder alle.")
        zeige_eintrag(fokus, verlauf[fokus], ist_letzter=(fokus == anzahl - 1))

    bildeingabe_ui()  # Bildeingabe

    frage = chat_eingabe("Stelle eine Frage zu den verfügbaren Themen...") or st.session_state.pop("naechste_frage", None)
    bild = st.session_state.pop("naechstes_bild", None) if frage else None
    suche_frage = st.session_state.pop("naechste_suche", None) if frage else None
    bild_meta = st.session_state.pop("naechste_bild_meta", {}) if frage else {}
    if frage and _V21_HZ and not bild:  # Hinweis-zuerst-Modus: Textfragen mit Hinweis zuerst (Bildfragen wie V20)
        _frage_hintergrund(frage)
    if frage:
        with st.chat_message("user"):
            if bild:
                st.image(bild, width=320)
            st.write(frage)
        with st.chat_message("assistant"):
            with st.status("Der Assistent arbeitet …", expanded=True) as status:
                start = time.perf_counter()
                import base64 as _b64
                _rp.BILD_ANHANG = _b64.b64encode(__import__('bildeingabe').verkleinere(bild)).decode() if bild else None
                _rp.RETRIEVAL_FRAGE = suche_frage if bild else None
                try:
                    ergebnis = beantworte_frage(frage, CHUNKS, fortschritt=fortschritt_anzeige(status))
                except Exception as fehler:  # kein Abbruch mit Traceback (z. B. Zeitüberschreitung des Sprachmodells)
                    print(f"FEHLER beantworte_frage: {type(fehler).__name__}: {fehler}")
                    status.update(label="Keine Antwort erzeugt", state="error", expanded=False)
                    st.error("Die Antwort konnte gerade nicht erzeugt werden (das Sprachmodell hat nicht rechtzeitig "
                             "geantwortet). Bitte stelle die Frage noch einmal.")
                    st.stop()
                finally:
                    _rp.BILD_ANHANG = None
                    _rp.RETRIEVAL_FRAGE = None
                status.update(label=f"Fertig · {sek(time.perf_counter() - start)}", state="complete", expanded=False)

        protokolliere_interaktion(st.session_state["sitzungs_id"], ergebnis, scaffolding_stufe_erreicht=1)
        if bild:
            st.session_state.setdefault("bilder", {})[len(st.session_state["verlauf"])] = bild
            st.session_state.setdefault("bild_meta", {})[len(st.session_state["verlauf"])] = bild_meta
        st.session_state["verlauf"].append(ergebnis)
        st.session_state["fokus"] = None  # neue Frage -> alle zeigen
        st.rerun()

    st.divider()
    if _ist_dev():  # technische Angaben nur im Entwicklermodus
        st.caption(f"Konfiguration: {_os.path.basename(KB_PFAD)} · {RETRIEVAL} · {_rp.SCAFFOLDING_VERSION}")
    col1, col2 = st.columns([3, 2])  # Platz für den längeren Knopftext
    with col1:
        st.caption(f"Bisher gestellte Fragen: {len(st.session_state['verlauf'])}")
    with col2:
        if st.button("Feedback zum Lernassistenten →", disabled=len(st.session_state["verlauf"]) == 0):
            st.session_state["seite"] = "fragebogen"
            st.rerun()


# =============================================================================
# SEITE 3: Abschlussfragebogen (TAM-basiert)
# =============================================================================
def seite_fragebogen():
    st.title("📋 Abschlussfragebogen")
    st.write(
        "Bitte bewerte die folgenden Aussagen zu deiner Erfahrung mit dem Lernassistenten. "
        "1 = stimme überhaupt nicht zu, 5 = stimme voll zu."
    )

    antworten = {}
    aktuelle_dimension = None
    for item in FRAGEBOGEN_ITEMS:
        if item["dimension"] != aktuelle_dimension:
            aktuelle_dimension = item["dimension"]
            st.subheader(aktuelle_dimension)
        antworten[item["id"]] = st.slider(item["text"], min_value=1, max_value=5, value=3, key=item["id"])

    freitext = st.text_area(
        "Möchtest du noch etwas ergänzen? (optional)",
        placeholder="Was hat gut funktioniert? Was war schwierig oder verwirrend?",
    )

    if st.button("Fragebogen absenden", type="primary"):
        if freitext.strip():
            antworten["FREITEXT"] = freitext.strip()
        speichere_fragebogen(st.session_state["sitzungs_id"], antworten)
        st.session_state["seite"] = "ende"
        st.rerun()


# =============================================================================
# SEITE 4: Abschluss
# =============================================================================
def seite_ende():
    st.title("✅ Vielen Dank für deine Teilnahme!")
    st.write(
        "Deine Antworten wurden gespeichert. Du kannst dieses Fenster jetzt schließen."
    )


# =============================================================================
# Routing
# =============================================================================
if st.session_state["seite"] == "start":
    seite_start()
elif st.session_state["seite"] == "chat":
    seite_chat()
elif st.session_state["seite"] == "fragebogen":
    seite_fragebogen()
elif st.session_state["seite"] == "ende":
    seite_ende()