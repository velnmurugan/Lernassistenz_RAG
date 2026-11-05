# V21-S – schnelle Fassung für die Pilotstudie

Antworten wie V20 (gleiche Pipeline, gleiche Prompts), nur anders gerechnet bzw. angezeigt. Zwei Schalter, standardmäßig AUS:

| Schalter | Wirkung |
|---|---|
| `LERNASSISTENT_RR_GPU=1` | Reranker (bge, 50 Kandidaten) auf der GPU statt CPU. Dafür wird qwen kurz aus der GPU entladen; danach lädt qwen beim nächsten Aufruf neu. Eine Sperre verhindert, dass Reranker und Sprachmodell gleichzeitig auf der GPU sind. Bei jedem Problem Rückfall auf die CPU (wie V20). |
| `LERNASSISTENT_HINWEIS_ZUERST=1` | Textfragen: Der Hinweis erscheint, sobald die Antwort geschrieben ist; Rechenprüfung und Abschlussprüfungen laufen im Hintergrund weiter. Lösung, Rückmeldung und Protokoll kommen aus dem vollständigen Ergebnis (wie V20). Bildfragen wie V20. |

Anlass: Profil 5. Nov 2026 (10 Fragen, RTX 3070 Laptop 8 GB): Reranker auf der CPU 50 % der Zeit (~33 s je Aufruf), Sprachmodell 47 %, Rest < 2 %.
Voraussetzung für RR_GPU: Test `test_reranker_gpu.py` zeigt gleiche Top-4 in allen Fällen.

Start: `bash skripte/laeufe/start_schnell.sh` (Port 8501, gleicher Cloudflare-Link). Unverändert V20: `bash skripte/laeufe/start_demo.sh`.
Zurück: `cp <datei>.vor_v21s <datei>` für app.py, lernassistent/reranker.py, lernassistent/rag_pipeline.py.

Hinweis zur Vorschau: Der vorab gezeigte Hinweis wird mit der Hinweisprüfung gegen die erste Lösung geprüft; ändert die Rechenprüfung danach die Lösung, wird der Hinweis im Endergebnis wie in V20 erneut geprüft. Weicht er ab, steht das im Terminal ("Vorab-Hinweis wich … ab").
Grenzen: mehrere Lernende gleichzeitig teilen sich die GPU (Sperre, Warteschlange); der Wechsel kostet je Reranker-Aufruf das Neuladen von qwen (~2–5 s).
