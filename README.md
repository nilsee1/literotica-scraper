# Literotica to EPUB Scraper & Generator

> [!IMPORTANT]
> **Disclaimer:**  
> Dieses Tool ist ein reines **Privatprojekt** zu privaten Archivierungs- und Lernzwecken.  
> Das **Urheberrecht (Copyright)** der jeweiligen Autoren und Plattformen muss stets zwingend beachtet werden! Die Erstellung von E-Books ist ausschließlich für den privaten, persönlichen Gebrauch bestimmt. Das Weiterverbreiten, Veröffentlichen oder die kommerzielle Nutzung fremder Werke ohne ausdrückliche Genehmigung der jeweiligen Urheber ist unzulässig. Die Verantwortung für die rechtmäßige Nutzung des Tools liegt vollumfänglich beim Nutzer.  
> *(100% Vibe Coded – USE AT OWN RISK)*

Ein vollständiges, lokal lauffähiges Python-Tool mit moderner Web-Oberfläche zum Extrahieren, Formatieren und Bündeln von Geschichten von [german.literotica.com](https://german.literotica.com) (und allgemeinen Literotica-Seiten) als standardkonforme `.epub`-E-Books.

---

## ✨ Features

- **Serien-Erkennung (Series URLs):**
  - Unterstützt direkte Serien-Links wie `https://www.literotica.com/series/se/hannah-familiensklavin` oder `/series/se/494520399`.
  - Löst Serien-Übersichtsseiten automatisch in alle enthaltenen Einzel-Geschichten auf und übernimmt automatisch den Serien-Titel und Autor als Standard-Metadaten.
- **Automatische Mehrseiten-Erkennung (Multi-Page):**
  - Erkennt auf Seite 1 automatisch, ob eine Geschichte über mehrere Seiten verteilt ist (z. B. 1 bis 17+ Seiten).
  - Ermittelt die Gesamtzahl via Paginierungs-Input (`<input name="page" max="...">`), Paginierungs-Links (`?page=X`) und Textheuristiken (`Seite 1 von X`).
  - Ruft alle Einzelseiten asynchron und parallel (mit Semaphore-Drosselung) ab.
- **Saubere Text- & Inhalts-Extraktion:**
  - Extrahiert den reinen Fließtext der Geschichte.
  - Entfernt störende Elemente wie Header, Fußzeilen, Paginierungs-Buttons, Werbung, Autoren-Statistiken, Kommentare und Tracking-Attribute.
  - Filtert Boilerplate- und Werbephrasen (z. B. Webcam-Hinweise, Copyright-Meldungen) zuverlässig heraus.
  - Erhält sinnvolle Formatierungen (Absätze `<p>`, Hervorhebungen `<em>`, `<strong>`).
- **Valider EPUB3-Generator:**
  - Erzeugt valide `.epub`-Dateien mit Inhaltsverzeichnis (TOC / NCX / NAV).
  - Jede URL wird zu einem eigenständigen Kapitel mit Titel, Untertitel (Autor & Originallink) und durchgehendem Text.
  - Integriertes, typografisch optimiertes Stylesheet für E-Reader (Kindle, Tolino, Kobo, Apple Books).
- **Fehlertoleranz:**
  - Schlägt der Abruf einer einzelnen URL fehl (z. B. 404), bricht die Erstellung nicht ab. Das E-Book wird mit den restlichen Geschichten erstellt und enthält für den Fehlerfall ein Platzhalter-Kapitel mit Hinweis.
- **Moderne Single-Page Web-Oberfläche:**
  - Responsive Oberfläche mit Tailwind CSS.
  - Voreingestellter Buchtitel mit aktuellem Datum (wird bei Serien-Links automatisch durch den Serien-Namen ersetzt).
  - Quick-Buttons zum Einfügen von Serien- oder Einzel-Beispielen.
  - Statusanzeige, animierter Ladebalken und Zeiterfassung während des Scrapings.
  - Automatischer Start des `.epub`-Downloads im Browser nach Fertigstellung.

---

## 🛠️ Tech-Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
- **HTTP-Client:** [httpx](https://www.python-httpx.org/) (asynchron mit Connection-Pooling)
- **HTML-Parsing:** [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/), [lxml](https://lxml.de/)
- **E-Book-Erstellung:** [ebooklib](https://github.com/aerkalov/ebooklib)
- **Frontend:** HTML5, [Tailwind CSS](https://tailwindcss.com/) (via CDN), Vanilla JavaScript

---

## 📁 Projektstruktur

```
├── app/
│   ├── main.py            # FastAPI-App, Endpunkte, Routing & Lifespan
│   ├── scraper.py         # Spezifischer Literotica-Scraper (Multi-Page & Text-Extraktion)
│   ├── epub_builder.py    # EPUB-Generierung (TOC, Kapitel, Metadaten, Stylesheet)
│   └── templates/
│       └── index.html     # Web-Interface mit Input-Formular & Ladeanzeige
├── requirements.txt       # Exakte Dependencies
├── README.md              # Lokale Startanweisungen und Dokumentation
└── .gitignore
```

---

## 🚀 Installation & Start (Empfohlen: Docker Compose)

Die einfachste, schnellste und **empfohlene Methode**, die Anwendung lokal oder auf einem Server zu betreiben. Es muss kein Python und keine Abhängigkeiten manuell eingerichtet werden.

### Variante A: Mit vorkonfiguriertem Docker-Image (Schnellste Methode)
Auf deinem Server benötigst du lediglich eine [`docker-compose.yml`](docker-compose.yml):

```yaml
services:
  literotica-scraper:
    image: ghcr.io/nilsee/literotica-scraper:latest
    container_name: literotica-scraper
    restart: unless-stopped
    ports:
      - "8000:8000"
```

Starte und aktualisiere den Container einfach mit:
```bash
# Neuestes Image von GitHub Container Registry herunterladen & starten
docker compose pull
docker compose up -d
```

### Variante B: Aus dem geklonten Repository starten
```bash
git clone https://github.com/nilsee/literotica-scraper.git
cd literotica-scraper

# Container im Hintergrund bauen und starten
docker compose up -d --build
```

### 📦 Image auf GitHub Container Registry (GHCR) bereitstellen / aktualisieren
Um das Docker-Image für `docker compose pull` auf externen Servern bereitzustellen:

1. **Einmalig bei GitHub Packages / GHCR anmelden:**
   *(Benötigt ein Personal Access Token (classic) unter GitHub > Settings > Developer settings > Personal access tokens mit `write:packages`-Berechtigung)*
   ```bash
   echo $CR_PAT | docker login ghcr.io -u nilsee --password-stdin
   ```

2. **Image bauen und zu GHCR pushen:**
   ```bash
   docker compose build
   docker compose push
   ```
   *(Alternativ wird das Image bei jedem Push auf den `main`-Branch automatisch via GitHub Actions gebaut und zu GHCR gepusht.)*

### Nützliche Docker-Befehle:
* **Status prüfen:** `docker compose ps`
* **Live-Logs einsehen:** `docker compose logs -f`
* **Stoppen:** `docker compose down`
* **Auf neueste Version aktualisieren:** `docker compose pull && docker compose up -d`

Nach dem Start ist die Web-Oberfläche erreichbar unter: **http://localhost:8000** bzw. **http://<server-ip>:8000**.

---

## 🛠️ Alternative: Lokale Python-Installation (für Entwicklung)

Falls du das Projekt ohne Docker direkt in einer Python-Umgebung ausführen möchtest:

### 1. Repository klonen & öffnen
```bash
git clone https://github.com/nilsee/literotica-scraper.git
cd literotica-scraper
```

### 2. Virtuelle Umgebung erstellen und aktivieren

**Unter Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Unter Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 4. Anwendung starten
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Öffne anschließend **http://127.0.0.1:8000** im Browser.

---

## 📖 Bedienung

1. **Buchtitel (optional):** Standardmäßig ist ein Titel mit dem heutigen Datum vorausgefüllt (wird bei Serien-Links automatisch durch den Namen der Serie ersetzt).
2. **Autor / Herausgeber (optional):** Name des Autors/Herausgebers für das Buch und den Dateinamen (wird bei Serien automatisch ermittelt).
3. **Jahr (optional):** Erscheinungsjahr des E-Books. Bleibt das Feld leer, wird automatisch das **aktuelle Kalenderjahr** verwendet.
4. **Story- oder Serien-URLs einfügen:**
   - Trage eine oder mehrere URLs in das Textfeld ein (eine URL pro Zeile).
   - Unterstützt sowohl Einzelgeschichten (`/s/...`) als auch vollständige Serien (`/series/se/...`).
5. **"EPUB generieren & herunterladen" klicken:**
   - Das Tool analysiert die Seiten, ruft mehrteilige Abschnitte parallel ab, formatiert den Text und baut die EPUB-Datei.
   - Die heruntergeladene Datei erhält das Format:
     ```text
     Autor - Titel.epub
     ```
     (Beispiel: `famfick - Hannah - Familiensklavin.epub`)

---

## 🔌 API-Endpunkte

### `GET /`
Rendert das Web-Frontend (`index.html`).

### `GET /api/health`
Einfacher Health-Check (`{"status": "ok"}`).

### `POST /api/generate`
Erstellt ein EPUB aus einer Liste von URLs.

**Request Body (JSON):**
```json
{
  "urls": [
    "https://www.literotica.com/series/se/hannah-familiensklavin"
  ],
  "book_title": "Hannah - Familiensklavin",
  "book_author": "famfick",
  "book_year": 2026
}
```

**Response:**
- `Content-Type: application/epub+zip`
- `Content-Disposition: attachment; filename="famfick - Hannah - Familiensklavin.epub"`
- Binäre `.epub`-Datei zum direkten Download.

