# Erzeugt alle Abbildungen 6–10 als PNG (600 dpi, 18 cm breit) und gibt die Kennwerte aus.
# In RStudio: Arbeitsverzeichnis auf diesen Ordner setzen (Session > Set Working Directory),
# dann diese Datei ausführen. Benötigt die Pakete ggplot2 und readxl.
for (f in c("Abb06_Urteile.R", "Abb07_Paarvergleiche.R", "Abb08_Fragetyp.R",
            "Abb09_Pruefpunkte.R", "Abb10_Hinweise_Fragetyp.R")) {
  code <- readLines(file.path("R", f), encoding = "UTF-8")
  code <- sub("^speichern <- FALSE", "speichern <- TRUE", code)
  eval(parse(text = code, encoding = "UTF-8"), envir = new.env())
}
source(file.path("R", "Statistik.R"), encoding = "UTF-8")
