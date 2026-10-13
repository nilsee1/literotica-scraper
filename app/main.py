"""
FastAPI Backend Application
Hauptanwendung für den Literotica-Scraper und EPUB-Generator.
"""

from contextlib import asynccontextmanager
from datetime import date
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx
from pydantic import BaseModel, Field

from app.epub_builder import build_epub, build_epub_filename, sanitize_title_for_filename
from app.scraper import fetch_series_info, is_series_url, scrape_story

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

# Pfade
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Literotica EPUB Scraper Backend gestartet.")
    yield
    logger.info("Literotica EPUB Scraper Backend beendet.")


app = FastAPI(
    title="Literotica to EPUB Generator",
    description="Web-Service zum Scrapen und Erstellen von EPUB-Büchern von German Literotica.",
    version="1.0.0",
    lifespan=lifespan,
)


class GenerateRequest(BaseModel):
    urls: list[str] = Field(..., description="Liste der zu scrapenden Literotica-URLs")
    book_title: Optional[str] = Field(None, description="Titel des resultierenden E-Books")
    book_author: Optional[str] = Field(None, description="Autor / Herausgeber des E-Books")
    book_year: Optional[int | str] = Field(None, description="Erscheinungsjahr des E-Books")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Rendert die Benutzeroberfläche.
    """
    current_date = date.today()
    default_title = f"Literotica Sammlung - {current_date.isoformat()}"
    default_year = current_date.year
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "default_title": default_title,
            "default_year": default_year,
        }
    )


@app.get("/api/health")
async def health_check():
    """
    Einfacher Status-Check.
    """
    return {"status": "ok", "service": "literotica-epub-generator"}


@app.post("/api/generate")
async def generate_epub(payload: GenerateRequest):
    """
    Empfängt Literotica-URLs, scrapt alle Seiten und liefert die .epub-Datei zum Download.
    """
    # 1. URLs validieren & bereinigen
    clean_urls: list[str] = []
    for raw_url in payload.urls:
        u = raw_url.strip()
        if u and (u.startswith("http://") or u.startswith("https://")):
            clean_urls.append(u)

    if not clean_urls:
        raise HTTPException(
            status_code=400,
            detail="Mindestens eine gültige HTTP/HTTPS-URL muss angegeben werden."
        )

    logger.info(f"Starte Generierung für {len(clean_urls)} eingegebene URL(s)")

    # 2. Asynchrones Auflösen von Serien-URLs & Scraping aller Geschichten
    timeout = httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=30.0)
    resolved_story_urls: list[str] = []
    detected_series_title: Optional[str] = None
    detected_series_author: Optional[str] = None
    scraped_stories = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        # A) Serien-URLs auflösen
        for url in clean_urls:
            if is_series_url(url):
                logger.info(f"Serien-URL erkannt, extrahiere Geschichten: {url}")
                series_data = await fetch_series_info(url, client=client)
                if series_data.get("error"):
                    logger.warning(f"Warnung bei Serie {url}: {series_data['error']}")
                
                if not detected_series_title and series_data.get("title"):
                    detected_series_title = series_data["title"]
                if not detected_series_author and series_data.get("author") and series_data["author"] != "Unbekannt":
                    detected_series_author = series_data["author"]

                for s_url in series_data.get("story_urls", []):
                    if s_url not in resolved_story_urls:
                        resolved_story_urls.append(s_url)
            else:
                if url not in resolved_story_urls:
                    resolved_story_urls.append(url)

        if not resolved_story_urls:
            raise HTTPException(
                status_code=400,
                detail="Keine Geschichten gefunden. Bitte überprüfe die angegebenen Links."
            )

        logger.info(f"Insgesamt {len(resolved_story_urls)} Geschichte(n) zu verarbeiten")

        # B) Geschichten nacheinander scrapen
        for url in resolved_story_urls:
            try:
                story_data = await scrape_story(url, client=client)
                scraped_stories.append(story_data)
            except Exception as exc:
                logger.error(f"Fehler bei Geschichte {url}: {exc}")
                scraped_stories.append({
                    "title": f"Fehler: {url}",
                    "author": "Unbekannt",
                    "url": url,
                    "total_pages": 0,
                    "content_html": f"<p class='error'>Unerwarteter Fehler: {exc}</p>",
                    "error": str(exc)
                })

    if not scraped_stories:
        raise HTTPException(
            status_code=500,
            detail="Keine Geschichten konnten abgerufen werden."
        )

    # 3. EPUB-Metadaten bestimmen: Nutzereingabe hat Vorrang vor erkanntem Serientitel
    current_date = date.today()

    # Jahr ermitteln (Standard: aktuelles Kalenderjahr)
    if payload.book_year is not None and str(payload.book_year).strip() != "":
        try:
            book_year = int(str(payload.book_year).strip())
        except ValueError:
            book_year = current_date.year
    else:
        book_year = current_date.year

    if payload.book_title and payload.book_title.strip():
        book_title = payload.book_title.strip()
    elif detected_series_title:
        book_title = detected_series_title
    else:
        book_title = f"Literotica Sammlung - {current_date.isoformat()}"

    if payload.book_author and payload.book_author.strip():
        book_author = payload.book_author.strip()
    elif detected_series_author:
        book_author = detected_series_author
    else:
        book_author = "Literotica Autoren"

    try:
        epub_bytes = build_epub(
            stories=scraped_stories,
            book_title=book_title,
            book_author=book_author,
            book_year=book_year
        )
    except Exception as exc:
        logger.exception("Fehler beim Erstellen der EPUB-Datei")
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Erstellen des EPUB3-Dokuments: {exc}"
        )

    # 4. Als Datei-Download im Format: 'Autor - Titel.epub' zurückliefern
    safe_filename = build_epub_filename(author=book_author, title=book_title)
    # RFC 5987 / URL-Encoded Filename Header für Sonderzeichen
    quoted_filename = quote(safe_filename)

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{quoted_filename}',
        "Content-Length": str(len(epub_bytes)),
        "Cache-Control": "no-cache, no-store, must-revalidate",
    }

    return Response(
        content=epub_bytes,
        media_type="application/epub+zip",
        headers=headers
    )
