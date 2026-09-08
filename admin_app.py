"""
admin_app.py
-------------
Admin-Werkzeug zum Aufbau der Wissensbasis per Upload — NUR für dich als
Forscherin/Forscher, NICHT für Proband:innen gedacht.

Läuft bewusst als SEPARATE App auf einem eigenen Port, damit Studierende
nie versehentlich auf diese Oberfläche zugreifen (siehe
Design_Entscheidungen_Literatur.md, Punkt 4: identische Wissensbasis für
alle Proband:innen — das gilt nur für die Studien-App app.py, nicht für
dieses Vorbereitungswerkzeug).

Start (auf einem ANDEREN Port als die Studien-App, z. B. 8502):
    streamlit run admin_app.py --server.port 8502 --server.fileWatcherType none
"""

import json
from pathlib import Path

import streamlit as st
from rag_pipeline import verarbeite_pdf_seitenweise, lade_wissensbasis

st.set_page_config(page_title="Admin: Wissensbasis verwalten", layout="wide")

ZIEL_DATEI = Path("knowledge_base.json")

st.title("🛠️ Admin: Wissensbasis aus PDFs aufbauen")
st.caption(
    "Dieses Werkzeug ist nur für dich (Forscher:in) gedacht — nicht für Proband:innen. "
    "Alle Teilnehmenden der Studie nutzen später dieselbe, hier erzeugte Wissensbasis."
)

# -----------------------------------------------------------------------
# Aktuellen Stand anzeigen
# -----------------------------------------------------------------------
with st.expander("📚 Aktuelle Wissensbasis anzeigen", expanded=False):
    if ZIEL_DATEI.exists():
        try:
            aktuelle_chunks = lade_wissensbasis(str(ZIEL_DATEI))
            themen = sorted(set(c["thema"] for c in aktuelle_chunks))
            st.write(f"**{len(aktuelle_chunks)} Chunks** aktuell gespeichert, Themen: {', '.join(themen)}")
            for c in aktuelle_chunks:
                st.markdown(f"**{c['id']}** [{c['thema']}]: {c['text'][:150]}{'...' if len(c['text']) > 150 else ''}")
        except Exception as e:
            st.error(f"Konnte aktuelle Wissensbasis nicht lesen: {e}")
    else:
        st.info("Noch keine Wissensbasis vorhanden.")

st.divider()

# -----------------------------------------------------------------------
# Upload
# -----------------------------------------------------------------------
st.subheader("1. PDF-Dateien hochladen")
hochgeladene_dateien = st.file_uploader(
    "Eine oder mehrere PDF-Dateien auswählen:",
    type=["pdf"],
    accept_multiple_files=True,
)

st.subheader("2. Chunking")
st.write(
    "Chunk-Grenzen werden **automatisch** anhand von inhaltlicher Ähnlichkeit "
    "zwischen aufeinanderfolgenden Sätzen bestimmt — kein Raten einer Satzanzahl mehr nötig "
    "(siehe Design_Entscheidungen_Literatur.md, Punkt 11)."
)

with st.expander("⚙️ Erweiterte Chunking-Einstellungen (normalerweise nicht nötig)"):
    chunking_methode = st.radio(
        "Methode:",
        ["Automatisch (empfohlen)", "Feste Satzanzahl (einfacher, gröber)"],
        horizontal=True,
    )
    if chunking_methode.startswith("Automatisch"):
        aehnlichkeits_schwelle = st.slider(
            "Ähnlichkeits-Schwelle:", min_value=0.2, max_value=0.8, value=0.55, step=0.05,
            help="Niedrigere Werte → weniger, größere Chunks (nur bei sehr deutlichem "
                 "Themenwechsel ein neuer Chunk). Höhere Werte → mehr, kleinere Chunks. "
                 "Startwert 0.55 ist nicht empirisch kalibriert — bei Bedarf anhand der "
                 "Vorschau unten anpassen.",
        )
        max_saetze_pro_chunk = st.slider("Sicherheitsobergrenze (Sätze):", min_value=3, max_value=15, value=8)
    else:
        aehnlichkeits_schwelle = 0.55
        max_saetze_pro_chunk = st.slider("Sätze pro Chunk:", min_value=1, max_value=6, value=3)

    ueberlapp_saetze = st.slider(
        "Überlappung zwischen benachbarten Chunks (Sätze):", min_value=0, max_value=3, value=1,
        help="Wie viele Sätze am Ende eines Chunks auch am Anfang des nächsten wiederholt werden "
             "(Prinzip nach Modran 2025, siehe Design_Entscheidungen_Literatur.md, Punkt 14). "
             "Mindert das Risiko, dass ein wichtiger Fakt genau an einer Chunk-Grenze 'verschwindet' "
             "— löst aber NICHT das Problem, dass Chunks nie über Seitengrenzen hinweg gebildet werden.",
    )

methode_intern = "semantisch" if chunking_methode.startswith("Automatisch") else "fest"

modus = st.radio(
    "Wie soll gespeichert werden?",
    ["Vorhandene Wissensbasis ERSETZEN", "Zu vorhandener Wissensbasis HINZUFÜGEN"],
    horizontal=True,
)

# -----------------------------------------------------------------------
# Verarbeitung + Vorschau
# -----------------------------------------------------------------------
if hochgeladene_dateien:
    if st.button("📄 PDFs verarbeiten und Vorschau anzeigen", type="primary"):
        neue_chunks = []
        naechste_nr = 1

        # Bei "Hinzufügen": Nummerierung an vorhandene Chunks anschließen,
        # damit keine doppelten IDs entstehen.
        if modus.startswith("Zu vorhandener") and ZIEL_DATEI.exists():
            bestehende = lade_wissensbasis(str(ZIEL_DATEI))
            vorhandene_nummern = [
                int(c["id"].split("_")[-1]) for c in bestehende
                if c["id"].startswith("pdf_") and c["id"].split("_")[-1].isdigit()
            ]
            naechste_nr = max(vorhandene_nummern, default=0) + 1

        fortschritt = st.progress(0.0, text="Verarbeite PDFs (bei 'Automatisch' inkl. Satz-Embeddings, kann dauern)...")
        for i, datei in enumerate(hochgeladene_dateien):
            dateiname_thema = datei.name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()

            try:
                seiten_chunks, anzahl_seiten, gliederung, hat_gliederung = verarbeite_pdf_seitenweise(
                    datei, max_saetze_pro_chunk=max_saetze_pro_chunk, fallback_thema=dateiname_thema,
                    methode=methode_intern, aehnlichkeits_schwelle=aehnlichkeits_schwelle,
                    ueberlapp_saetze=ueberlapp_saetze,
                )
            except Exception as e:
                st.warning(f"⚠️ {datei.name}: Fehler beim Lesen ({e}) — übersprungen.")
                continue

            if not seiten_chunks:
                st.warning(f"⚠️ {datei.name}: Kein Text extrahiert (evtl. gescanntes PDF ohne OCR) — übersprungen.")
                continue

            datei_chunks = []
            for sc in seiten_chunks:
                datei_chunks.append({
                    "id": f"pdf_{naechste_nr:04d}",
                    "thema": sc["thema"],
                    "text": sc["text"],
                    "quelle_datei": datei.name,
                    "seite": sc["seite"],
                })
                naechste_nr += 1

            neue_chunks.extend(datei_chunks)

            if hat_gliederung:
                anzahl_themen = len(set(c["thema"] for c in datei_chunks))
                st.success(
                    f"✅ {datei.name}: {anzahl_seiten} Seite(n) → {len(datei_chunks)} Chunks, "
                    f"**{anzahl_themen} Kapitel/Abschnitte automatisch erkannt** "
                    f"(aus PDF-Gliederung: {', '.join(t for t, _ in gliederung[:5])}{', ...' if len(gliederung) > 5 else ''})"
                )
            else:
                st.info(
                    f"ℹ️ {datei.name}: {anzahl_seiten} Seite(n) → {len(datei_chunks)} Chunks. "
                    f"**Keine PDF-Gliederung gefunden** — alle Chunks erhalten einheitlich "
                    f"das Thema '{dateiname_thema}' (aus dem Dateinamen). Bei einem thematisch "
                    f"breiten Dokument ohne Gliederung ggf. manuell in kleinere, "
                    f"themenreine PDFs aufteilen."
                )
            fortschritt.progress((i + 1) / len(hochgeladene_dateien))

        st.session_state["admin_neue_chunks"] = neue_chunks
        st.session_state["admin_modus"] = modus

# -----------------------------------------------------------------------
# Vorschau + Bestätigung
# -----------------------------------------------------------------------
if "admin_neue_chunks" in st.session_state and st.session_state["admin_neue_chunks"]:
    st.divider()
    st.subheader("3. Vorschau — bitte vor dem Speichern prüfen")

    neue_chunks = st.session_state["admin_neue_chunks"]
    st.write(f"**{len(neue_chunks)} neue Chunks** bereit zum Speichern.")

    # Themen-Übersicht zuerst -- bei einem umfangreichen Handbuch mit vielen
    # Kapiteln ist eine Chunk-für-Chunk-Vorschau allein nicht mehr praktikabel;
    # die Themenverteilung zeigt auf einen Blick, ob die Gliederungserkennung
    # sinnvoll gegriffen hat.
    themen_uebersicht = {}
    for c in neue_chunks:
        themen_uebersicht[c["thema"]] = themen_uebersicht.get(c["thema"], 0) + 1

    st.markdown(f"**{len(themen_uebersicht)} Themen/Kapitel erkannt:**")
    for thema, anzahl in sorted(themen_uebersicht.items(), key=lambda x: -x[1])[:30]:
        st.markdown(f"- {thema}: {anzahl} Chunks")
    if len(themen_uebersicht) > 30:
        st.caption(f"... und {len(themen_uebersicht) - 30} weitere Themen/Kapitel.")

    # WICHTIG: Speichern-Button steht bewusst HIER, direkt nach der (billigen)
    # Themen-Übersicht — NICHT erst nach der Detail-Vorschau. Bei sehr großen
    # Wissensbasen (mehrere zehntausend Chunks) würde eine ungebremste
    # Detail-Vorschau den Browser/die Seite so lange blockieren, dass der
    # Speichern-Button praktisch unerreichbar wirkt (siehe eigene
    # Fehlerbeobachtung mit einem 1721-seitigen Handbuch, 25.322 Chunks).
    st.divider()
    if st.button("💾 In knowledge_base.json speichern", type="primary"):
        if st.session_state["admin_modus"].startswith("Zu vorhandener") and ZIEL_DATEI.exists():
            bestehende = lade_wissensbasis(str(ZIEL_DATEI))
            gesamt_chunks = bestehende + neue_chunks
        else:
            gesamt_chunks = neue_chunks

        ausgabe = {
            "_hinweis": "Erzeugt über admin_app.py (PDF-Upload durch Forscher:in).",
            "chunks": gesamt_chunks,
        }
        with open(ZIEL_DATEI, "w", encoding="utf-8") as f:
            json.dump(ausgabe, f, ensure_ascii=False, indent=2)

        st.success(f"✅ '{ZIEL_DATEI}' gespeichert: {len(gesamt_chunks)} Chunks insgesamt.")
        del st.session_state["admin_neue_chunks"]
        st.info("Die Studien-App (app.py) lädt die Wissensbasis bei jeder neuen Frage automatisch "
                "neu — ein Browser-Refresh der Studien-App genügt, kein Neustart nötig.")

    st.divider()

    # Detail-Vorschau: bewusst auf eine repräsentative STICHPROBE begrenzt
    # (gleichmäßig über die gesamte Liste verteilt), nicht auf alle Chunks --
    # sonst würde diese Sektion bei zehntausenden Chunks extrem lange
    # brauchen oder die Seite einfrieren, unabhängig davon, ob der Expander
    # eingeklappt ist (Streamlit führt den Code im Expander trotzdem aus).
    MAX_VORSCHAU = 30
    if len(neue_chunks) <= MAX_VORSCHAU:
        stichprobe = neue_chunks
        vorschau_hinweis = f"Alle {len(neue_chunks)} Chunks"
    else:
        schritt = max(1, len(neue_chunks) // MAX_VORSCHAU)
        stichprobe = neue_chunks[::schritt][:MAX_VORSCHAU]
        vorschau_hinweis = f"Stichprobe: {len(stichprobe)} von {len(neue_chunks)} Chunks (gleichmäßig verteilt)"

    with st.expander(f"🔍 Chunk-Vorschau — {vorschau_hinweis}", expanded=(len(neue_chunks) <= 12)):
        if len(neue_chunks) > MAX_VORSCHAU:
            st.caption(
                "Nur eine Stichprobe wird angezeigt, um die Seite reaktionsfähig zu halten. "
                "ALLE Chunks werden beim Speichern trotzdem vollständig übernommen."
            )
        farben = ["#e8f0fe", "#fce8e6", "#e6f4ea", "#fef7e0", "#f3e8fd"]
        spalten = st.columns(3)
        for i, c in enumerate(stichprobe):
            farbe = farben[i % len(farben)]
            seiten_info = f" · S. {c['seite']}" if "seite" in c else ""
            with spalten[i % 3]:
                st.markdown(
                    f"<div style='background-color:{farbe}; color:#111; padding:10px; "
                    f"border-radius:8px; margin-bottom:10px; min-height:100px;'>"
                    f"<b>{c['id']}</b> [{c['thema']}]<br>"
                    f"<small>Quelle: {c['quelle_datei']}{seiten_info}</small><br>{c['text']}</div>",
                    unsafe_allow_html=True,
                )