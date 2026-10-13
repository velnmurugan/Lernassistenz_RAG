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

import streamlit as st
from rag_pipeline import (
    lade_wissensbasis, beantworte_frage, protokolliere_interaktion,
    speichere_fragebogen, FRAGEBOGEN_ITEMS,
)
from ideen_feedback import gib_feedback, protokolliere_idee, idee_moeglich, MAX_VERSUCHE

st.set_page_config(page_title="KI-Lernassistent", layout="centered")

if "seite" not in st.session_state:
    st.session_state["seite"] = "start"
if "verlauf" not in st.session_state:
    st.session_state["verlauf"] = []
if "sitzungs_id" not in st.session_state:
    st.session_state["sitzungs_id"] = ""

CHUNKS = lade_wissensbasis("knowledge_base.json")


# =============================================================================
# SEITE 1: Start / Einverständnis / Sitzungs-ID
# =============================================================================
def seite_start():
    st.title("🎓 KI-Lernassistent für die technische Ausbildung")
    st.write(
        "Willkommen! Dieser Lernassistent beantwortet Fragen zu ausgewählten "
        "Themen der technischen Ausbildung (z. B. elektrische Sicherheit, "
        "SPS-Grundlagen, Sensorik, Pneumatik) auf Basis geprüfter Lernmaterialien."
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
        if not eintrag["vollstaendig_geparst"]:
            # Fallback: Modell hat das Stufen-Format nicht eingehalten,
            # volle Antwort direkt zeigen statt mit leeren Stufen zu verwirren.
            st.write(eintrag["loesung"])
        else:
            aktuelle_stufe = st.session_state[stufe_key]
            st.markdown(f"💡 **Hinweis:** {eintrag['hinweis']}")
            zeige_ideen(versuche, 1)

            if aktuelle_stufe >= 2:
                st.markdown(f"✅ **Lösung:** {eintrag['loesung']}")

            if (ist_letzter and aktuelle_stufe < 2 and len(versuche) < MAX_VERSUCHE
                    and idee_moeglich(eintrag)):
                ideen_eingabe(idx, eintrag, versuche, aktuelle_stufe)

            if aktuelle_stufe == 1:
                if st.button("✅ Lösung anzeigen", key=f"btn_loesung_{idx}"):
                    st.session_state[stufe_key] = 2
                    protokolliere_interaktion(st.session_state["sitzungs_id"], eintrag, scaffolding_stufe_erreicht=2)
                    st.rerun()

        if eintrag["quellen"] and (not eintrag["vollstaendig_geparst"] or st.session_state[stufe_key] >= 2 or not eintrag["genuegend_relevanz"]):
            quellen_text = ", ".join(f"{q['id']} ({q['thema']})" for q in eintrag["quellen"])
            st.caption(f"📎 Quellen: {quellen_text}")
        if eintrag["sicherheitshinweis"]:
            st.warning(
                "⚠️ Dieses Thema kann sicherheitsrelevant sein. "
                "Bitte zusätzlich mit einer Lehrkraft besprechen."
            )


def seite_chat():
    st.title("🎓 KI-Lernassistent")
    st.caption(f"Sitzung: {st.session_state['sitzungs_id']}")

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
        with st.spinner("Der Assistent sucht eine Antwort..."):
            ergebnis = beantworte_frage(frage, CHUNKS)

        protokolliere_interaktion(st.session_state["sitzungs_id"], ergebnis, scaffolding_stufe_erreicht=1)
        st.session_state["verlauf"].append(ergebnis)
        st.rerun()

    st.divider()
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