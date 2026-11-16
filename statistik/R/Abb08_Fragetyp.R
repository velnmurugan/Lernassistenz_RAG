# =====================================================================
# Abbildung 8 – Punktanteil nach Fragetyp (270 Buchfragen).
# Balken: menschliche Bewertung; Fehlerbalken: Spannweite (Minimum bis
# Maximum) über alle drei Bewertungen (menschlich, Gemini, Mistral).
# Läuft im jamovi-Modul "Rj Editor" (`data` = geöffnete Tabelle) und in R.
# =====================================================================
if (!is.data.frame(data)) data <- readxl::read_excel("Daten_Beitrag_jamovi.xlsx", sheet = "Daten")
library(ggplot2)
speichern <- FALSE
breite_cm <- 18; hoehe_cm <- 11   # Größe der Abbildung im Beitrag
# Die Abbildung wird immer in Originalgröße gezeichnet. In jamovi (Rj Editor) dafür im Zahnrad-Menü
# "Figure size (px)" Width = 512 und Height = 314 eintragen (1 px = 1/72 Zoll; 18 × 11 cm).
skal <- 1   # Verkleinerungsfaktor für Schrift und Linien (1 = wie im Beitrag)

d <- as.data.frame(data)
d <- d[as.character(d$Typ) != "Außerhalb", ]
punkte <- function(x) c(ja = 1, teilweise = 0.5, nein = 0)[as.character(x)]

typen <- c("Konzept", "Fakt", "Rechnung", "Tabellenabfrage", "Aufzählung")
bedingungen <- c(qwen_ohne = "qwen ohne RAG", qwen_mit = "qwen mit RAG",
                 GPT_ohne  = "GPT ohne RAG",  GPT_mit  = "GPT mit RAG")
bewertungen <- c("Mensch", "Gemini", "Mistral")

tab <- do.call(rbind, lapply(typen, function(t) {
  dt <- d[as.character(d$Typ) == t, ]
  do.call(rbind, lapply(names(bedingungen), function(b) {
    w <- sapply(bewertungen, function(r) mean(punkte(dt[[paste0(b, "_", r)]]), na.rm = TRUE))
    data.frame(Typ = paste0(t, "\n(n = ", nrow(dt), ")"), Bedingung = bedingungen[b],
               Wert = w[["Mensch"]], Min = min(w), Max = max(w))
  }))
}))
tab$Typ <- factor(tab$Typ, levels = unique(tab$Typ))
tab$Bedingung <- factor(tab$Bedingung, levels = bedingungen)

farben  <- c("qwen ohne RAG" = "#F4C38A", "qwen mit RAG" = "#D55E00",
             "GPT ohne RAG"  = "#A9CCE3", "GPT mit RAG"  = "#1F4E79")
prozent <- function(x) paste0(round(x * 100), " %")
pd <- position_dodge(width = 0.85)

p <- ggplot(tab, aes(x = Typ, y = Wert, fill = Bedingung)) +
  geom_col(position = pd, width = 0.82) +
  geom_errorbar(aes(ymin = Min, ymax = Max), position = pd, width = 0.25, colour = "#333333", linewidth = 0.4 * skal) +
  scale_fill_manual(values = farben) +
  scale_y_continuous(labels = prozent, breaks = seq(0, 1, 0.2), limits = c(0, 1.02)) +
  guides(fill = guide_legend(nrow = 2, byrow = TRUE)) +
  labs(x = NULL, y = "Punktanteil", fill = NULL) +
  theme_classic(base_size = 10 * skal) +
  theme(legend.position = "top",
        legend.text = element_text(size = 10 * skal, margin = margin(r = 8 * skal, l = 4 * skal)),
        legend.key.size = unit(0.45 * skal, "cm"),
        axis.text = element_text(size = 10 * skal), axis.title.y = element_text(size = 12 * skal))
if (speichern) {
  ggsave("Abb08_Fragetyp.png", p, width = breite_cm, height = hoehe_cm, units = "cm", dpi = 600, bg = "white")
} else {
  grid::grid.newpage()
  print(p, vp = grid::viewport(width = grid::unit(breite_cm * skal, "cm"), height = grid::unit(hoehe_cm * skal, "cm")))
}
