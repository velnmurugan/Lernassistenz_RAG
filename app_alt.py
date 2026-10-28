"""
app.py
------
KI-Lernassistent — Studien-Prototyp für die Pilotstudie (Phase 2).

Ablauf für Proband:innen:
  1. Sitzungs-ID eingeben (pseudonymisiert, keine Klarnamen)
  2. Fragen an den Lernassistenten stellen (beliebig viele)
     Pro Antwort: Hinweis -> optional "Deine Idee?" mit Rückmeldung
     (ideen_feedback.py) -> Lösung mit Begründung (V4, 2 Stufen)
  3. Abschließenden Fragebogen ausfüllen (TAM-basiert, Davis 1989)

Start: streamlit run app.py --server.fileWatcherType none
(Ollama muss vorher laufen, Modell: qwen3.5:9b)
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import re
import time
import streamlit as st
from rag_pipeline import (
    lade_wissensbasis, beantworte_frage, protokolliere_interaktion,
    speichere_fragebogen, FRAGEBOGEN_ITEMS,
)
from ideen_feedback import gib_feedback, protokolliere_idee, idee_moeglich, MAX_VERSUCHE

APP_NAME = "KI-Lernassistent"  # Arbeitsname, an einer Stelle änderbar

st.set_page_config(page_title=APP_NAME, page_icon="🎓", layout="centered")

if "seite" not in st.session_state:
    st.session_state["seite"] = "start"
if "verlauf" not in st.session_state:
    st.session_state["verlauf"] = []
if "sitzungs_id" not in st.session_state:
    st.session_state["sitzungs_id"] = ""

import os as _os, rag_pipeline as _rp  # Test: Wissensbasis/Retrieval per Umgebungsvariable
# Standard = aktuelle Version V10a (Fischer-Wissensbasis, Hybrid + Wissensgraph + Reranker).
# Andere Konfiguration weiter über Umgebungsvariablen, z. B. für Böge:
#   LERNASSISTENT_KB=daten/wissensbasen/knowledge_base_boege.json streamlit run app.py ...
KB_OPTIONEN = {  # Anzeigename -> Datei (nur vorhandene Dateien erscheinen in der Auswahl)
    "Beide Bücher (experimentell)": "daten/wissensbasen/knowledge_base_fischer_boege.json",
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
    st.title(f"🎓 {APP_NAME} für die technische Ausbildung")
    st.write(
        "Willkommen! Dieser Lernassistent beantwortet Fragen zu ausgewählten "
        "Themen der technischen Ausbildung (siehe Liste der verfügbaren Themen im Chat) "
        "auf Basis geprüfter Lernmaterialien."
    )

    with st.expander("ℹ️ Hinweise zur Teilnahme", expanded=True):
        st.markdown(
            "- Deine Eingaben werden **pseudonymisiert** gespeichert (über die Sitzungs-ID unten), "
            "nicht mit deinem Namen verknüpft.\n"
            "- Fragen, Antworten, deine eingegebenen Ideen und deine Bewertung im Abschlussfragebogen werden für die "
            "wissenschaftliche Auswertung dieser Pilotstudie verwendet.\n"
            "- Du kannst die Teilnahme jederzeit ohne Angabe von Gründen abbrechen.\n"
            "- Der Assistent antwortet **nur** auf Basis der hinterlegten Lernmaterialien. "
            "Findet er keine passende Quelle, sagt er das ehrlich, statt zu raten."
        )

    st.text_input(
        "Sitzungs-ID (z. B. von deiner Lehrkraft vergeben, kein Klarname):",
        key="sitzungs_id_eingabe",
        value="TEST-Demo",  # TEST-Präfix: Demo-Sitzungen lassen sich aus interaktionen.csv herausfiltern
        placeholder="z. B. TN-07",
    )

    einverstanden = st.checkbox("Ich habe die Hinweise gelesen und bin mit der Teilnahme einverstanden.")

    if st.button("Starten", type="primary", disabled=not einverstanden):
        eingabe = st.session_state.get("sitzungs_id_eingabe", "").strip()
        if not eingabe:
            st.error("Bitte gib eine Sitzungs-ID ein.")
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

    def rueckruf(phase, ereignis, dauer=None):
        if phase not in zeilen:
            zeilen[phase] = status.empty()
        if ereignis == "start":
            zeilen[phase].markdown(f"⏳ {PHASEN[phase][0]} …")
        else:
            zeilen[phase].markdown(f"✓ {PHASEN[phase][1]} · {sek(dauer)}")
    return rueckruf


def zeige_zeiten(eintrag):
    """Aufklappbare Zeitübersicht je Antwort ("Gedacht für x Sekunden")."""
    zeiten = eintrag.get("zeiten") or {}
    if not zeiten:
        return
    gesamt = sum(zeiten.values())
    with st.expander(f"⏱ Gedacht für {sek(gesamt)}"):
        for phase, (_, fertig) in PHASEN.items():
            if phase in zeiten:
                st.markdown(f"- {fertig}: **{sek(zeiten[phase])}**")


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


def zeige_loesung(loesung):
    antwort, begruendung, vermerk = zerlege_loesung(loesung)
    st.markdown(f"✅ **Lösung:** {antwort}")
    if begruendung:
        st.markdown(f"**Begründung:** {begruendung}")
    if vermerk:
        st.caption(f"🔍 {vermerk}")


def zeige_quellen(eintrag):
    """Quellenzeile plus aufklappbare Textstellen (Buch, Seite, Auszug)."""
    chunks = eintrag.get("top_chunks") or []
    if not chunks:
        return
    with st.expander(f"📎 Quellen ({len(chunks)})"):
        for i, c in enumerate(chunks, start=1):
            seite = c.get("seite") or c.get("pdf_seite")
            kopf = (f"**Quelle {i}:** " + (f"{c['buch']} · " if c.get("buch") else "")
                    + f"{c.get('thema', '')}" + (f" · S. {seite}" if seite else ""))
            st.markdown(kopf)
            st.text((c.get("text") or "")[:700] + (" …" if len(c.get("text") or "") > 700 else ""))


URTEIL_SYMBOL = {"richtig": "✅", "teilweise": "🟡", "falsch": "🔁", "keine_idee": "💬"}


def zeige_ideen(versuche, stufe):
    """Ideen + Rückmeldungen, die auf dieser Stufe abgegeben wurden (chronologisch
    an der Stelle, an der sie entstanden sind)."""
    for v in versuche:
        if v["stufe"] == stufe:
            st.markdown(f"💭 **Deine Idee:** {v['idee']}")
            st.markdown(f"{URTEIL_SYMBOL.get(v['urteil'], '💬')} **Rückmeldung:** {v['rueckmeldung']}")


def ideen_eingabe(idx, eintrag, versuche, aktuelle_stufe):
    """Optionales Feld "Deine Idee?" (Scaffolding-Spezifikation S-v1, D2). Der Key
    enthält die Versuchsnummer, damit das Feld nach dem Absenden leer ist."""
    n = len(versuche)
    text = st.text_area(
        "💭 Deine Idee? (optional) — Was glaubst du, wie die Antwort lautet?",
        key=f"idee_text_{idx}_{n}", height=80,
        placeholder="Schreib deine Vermutung in eigenen Worten …",
    )
    if st.button("Idee prüfen lassen", key=f"btn_idee_{idx}_{n}"):
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
    (V4: Hinweis -> [Deine Idee? + Rückmeldung] -> Lösung). Stufe 1 = Hinweis,
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
        st.write(eintrag["frage"])

    with st.chat_message("assistant"):
        verweigert = eintrag.get("status") in ("GATE", "NICHT_IM_MATERIAL")
        if verweigert:
            # Keine Treffer im Lernmaterial: ehrliche Rückmeldung statt Stufen und Quellen
            st.info(eintrag["loesung"])
        elif not eintrag["vollstaendig_geparst"]:
            # Fallback: Modell hat das Stufen-Format nicht eingehalten,
            # volle Antwort direkt zeigen statt mit leeren Stufen zu verwirren.
            zeige_loesung(eintrag["loesung"])
        else:
            aktuelle_stufe = 2 if st.session_state.get("loesung_direkt") else st.session_state[stufe_key]
            st.markdown(f"💡 **Hinweis:** {eintrag['hinweis']}")
            zeige_ideen(versuche, 1)

            if aktuelle_stufe >= 2:
                zeige_loesung(eintrag["loesung"])

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
            zeige_quellen(eintrag)
        zeige_zeiten(eintrag)
        if eintrag["sicherheitshinweis"]:
            st.warning(
                "⚠️ Dieses Thema kann sicherheitsrelevant sein. "
                "Bitte zusätzlich mit einer Lehrkraft besprechen."
            )


def seite_chat():
    st.title(f"🎓 {APP_NAME}")
    st.caption(f"Sitzung: {st.session_state['sitzungs_id']}")
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

    anzahl = len(st.session_state["verlauf"])
    for idx, eintrag in enumerate(st.session_state["verlauf"]):
        zeige_eintrag(idx, eintrag, ist_letzter=(idx == anzahl - 1))

    frage = st.chat_input("Stelle eine Frage zu den verfügbaren Themen...")
    if frage:
        with st.chat_message("user"):
            st.write(frage)
        with st.chat_message("assistant"):
            with st.status("Der Assistent arbeitet …", expanded=True) as status:
                start = time.perf_counter()
                ergebnis = beantworte_frage(frage, CHUNKS, fortschritt=fortschritt_anzeige(status))
                status.update(label=f"Fertig · {sek(time.perf_counter() - start)}", state="complete", expanded=False)

        protokolliere_interaktion(st.session_state["sitzungs_id"], ergebnis, scaffolding_stufe_erreicht=1)
        st.session_state["verlauf"].append(ergebnis)
        st.rerun()

    st.divider()
    st.caption(f"Konfiguration: {_os.path.basename(KB_PFAD)} · {RETRIEVAL} · {_rp.SCAFFOLDING_VERSION}")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Bisher gestellte Fragen: {len(st.session_state['verlauf'])}")
    with col2:
        if st.button("Zur Bewertung →", type="primary", disabled=len(st.session_state["verlauf"]) == 0):
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