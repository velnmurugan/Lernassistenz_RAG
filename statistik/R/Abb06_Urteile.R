# =====================================================================
# Abbildung 6 – Verteilung der Urteile je Bedingung und Bewertung
# (270 Buchfragen). Läuft unverändert im jamovi-Modul "Rj Editor"
# (dort ist `data` die geöffnete Tabelle) und in R/RStudio.
# =====================================================================
if (!is.data.frame(data)) data <- readxl::read_excel("Daten_Beitrag_jamovi.xlsx", sheet = "Daten")
library(ggplot2)
speichern <- FALSE          # TRUE: PNG mit 600 dpi neben die Excel-Datei schreiben
breite_cm <- 18; hoehe_cm <- 10   # Größe der Abbildung im Beitrag
# Die Abbildung wird immer in Originalgröße gezeichnet. In jamovi (Rj Editor) dafür im Zahnrad-Menü
# "Figure size (px)" Width = 512 und Height = 314 eintragen (1 px = 1/72 Zoll; 18 × 11 cm).
skal <- 1   # Verkleinerungsfaktor für Schrift und Linien (1 = wie im Beitrag)
label_mensch <- "Human 1"   # Beschriftung der menschlichen Bewertung

d <- as.data.frame(data)
d <- d[as.character(d$Typ) != "Außerhalb", ]          # nur Buchfragen

bedingungen <- c(qwen_ohne = "qwen ohne RAG", qwen_mit = "qwen mit RAG",
                 GPT_ohne  = "GPT ohne RAG",  GPT_mit  = "GPT mit RAG")
bewertungen <- c(Mensch = label_mensch, Gemini = "Gemini", Mistral = "Mistral")
urteile     <- c(ja = "richtig", teilweise = "teilweise richtig", nein = "falsch")

tab <- do.call(rbind, lapply(names(bedingungen), function(b) {
  do.call(rbind, lapply(names(bewertungen), function(r) {
    x <- as.character(d[[paste0(b, "_", r)]])
    n <- sapply(names(urteile), function(u) sum(x == u, na.rm = TRUE))
    data.frame(Bedingung = bedingungen[b], Bewertung = bewertungen[r],
               Urteil = urteile[names(urteile)], n = as.numeric(n),
               Anteil = as.numeric(n) / sum(n))
  }))
}))
tab$Bedingung <- factor(tab$Bedingung, levels = bedingungen)
tab$Bewertung <- factor(tab$Bewertung, levels = bewertungen)
tab$Urteil    <- factor(tab$Urteil, levels = rev(urteile))   # richtig unten
tab$Label     <- ifelse(tab$n >= 15, tab$n, "")             # kleine Segmente ohne Zahl

farben <- c("richtig" = "#1A9850", "teilweise richtig" = "#F2B600", "falsch" = "#D73027")
prozent <- function(x) paste0(round(x * 100), " %")

p <- ggplot(tab, aes(x = Bewertung, y = Anteil, fill = Urteil)) +
  geom_col(width = 0.8) +
  geom_text(aes(label = Label), position = position_stack(vjust = 0.5),
            colour = "white", size = 3 * skal) +
  facet_wrap(~ Bedingung, nrow = 1, strip.position = "bottom") +
  scale_fill_manual(values = farben, breaks = urteile) +
  scale_y_continuous(labels = prozent, breaks = seq(0, 1, 0.2),
                     expand = expansion(mult = c(0, 0.01))) +
  labs(x = NULL, y = paste0("Anteil der Antworten (", nrow(d), " Buchfragen)"), fill = NULL) +
  theme_classic(base_size = 10 * skal) +
  theme(legend.position = "top",
        legend.text = element_text(size = 9.5 * skal, margin = margin(r = 8 * skal, l = 4 * skal)),
        legend.key.size = unit(0.45 * skal, "cm"),
        axis.text.x = element_text(angle = 45, hjust = 1, size = 8.5 * skal),
        axis.text.y = element_text(size = 9 * skal),
        axis.title.y = element_text(size = 10.5 * skal),
        strip.placement = "outside", strip.background = element_blank(),
        strip.text = element_text(face = "bold", size = 10.5 * skal),
        panel.spacing = unit(0.6 * skal, "cm"))
if (speichern) {
  ggsave("Abb06_Urteile.png", p, width = breite_cm, height = hoehe_cm, units = "cm", dpi = 600, bg = "white")
} else {
  grid::grid.newpage()
  print(p, vp = grid::viewport(width = grid::unit(breite_cm * skal, "cm"), height = grid::unit(hoehe_cm * skal, "cm")))
}
