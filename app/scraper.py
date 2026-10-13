"""
Literotica Scraper Module
Extrahiert Geschichten von german.literotica.com (sowie literotica.com allgemein)
inklusive automatischer Erkennung und Zusammenführung mehrseitiger Geschichten.
"""

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag
import httpx

logger = logging.getLogger("literotica_scraper")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://german.literotica.com/",
}

SAFE_INLINE_TAGS = {"em", "strong", "i", "b", "u", "br", "sub", "sup"}

UNWANTED_PHRASES = [
    "Anmeldenum",
    "Zur klassischen Ansicht wechseln",
    "Das Update vom November 2025 ist live",
    "Spannende Neuerungen für Autorenprofile",
    "Probiere die kostenlosen LITEROTICA WEBCAMS",
    "Sprache auswählen",
    "Alle Inhalte © Copyright",
    "Copyright 1996-",
    "Literotica ist eine eingetragene Marke",
    "DMCA",
    "2257",
    "Live-Webcams",
    "Jetzt online!",
    "de es en it",
]


def is_series_url(url: str) -> bool:
    """
    Prüft, ob eine URL auf eine Serie verweist (z. B. /series/se/... oder /series/...).
    """
    clean = url.strip()
    parsed = urlparse(clean)
    return "/series/" in parsed.path.lower()


def clean_base_url(url: str) -> str:
    """
    Entfernt Query-Parameter (z.B. ?page=2), Anker und Trailing-Slashes,
    damit das Scraping verlässlich von Seite 1 startet.
    """
    clean = url.strip()
    parsed = urlparse(clean)
    normalized_path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, normalized_path, "", "", ""))


def extract_metadata(soup: BeautifulSoup, base_url: str) -> tuple[str, str]:
    """
    Extrahiert den bereinigten Titel und den Autorennamen aus der Seite.
    """
    # 1. Titel extrahieren
    title = ""
    # Erst im <article> nach h1 suchen, dann allgemein nach h1
    article = soup.find("article")
    h1 = (article.find("h1") if article else None) or soup.find("h1")
    if h1:
        raw_title = h1.get_text()
        # HTML-Kommentare und Whitespace bereinigen
        cleaned = re.sub(r"<!--.*?-->", "", raw_title).strip()
        if cleaned:
            title = cleaned

    if not title:
        meta_og = soup.find("meta", property="og:title")
        if meta_og and meta_og.get("content"):
            title = str(meta_og["content"]).strip()
            # Entferne eventuelle Zusätze wie " - Literotica.com"
            title = re.sub(r"\s*-\s*Literotica(?:\.com)?.*$", "", title, flags=re.I).strip()

    if not title and soup.title:
        title = soup.title.get_text().strip()
        title = re.sub(r"\s*-\s*Literotica(?:\.com)?.*$", "", title, flags=re.I).strip()

    if not title:
        # Fallback: Aus dem URL-Pfad-Slug ableiten
        path_slug = urlparse(base_url).path.split("/")[-1]
        title = path_slug.replace("-", " ").replace("_", " ").title() if path_slug else "Unbenannte Geschichte"

    # 2. Autor extrahieren
    author = "Unbekannt"
    # Suche nach Autor-Links (z.B. /authors/Michael_Hinze oder /members/...)
    author_links = soup.find_all("a", href=re.compile(r"/(?:authors|members)/"))
    for link in author_links:
        link_text = link.get_text(strip=True)
        # Filter Link-Texte heraus, die nur Statistiken oder Zahlen sind
        if link_text and not any(kw in link_text.lower() for kw in ["geschichten", "anhänger", "stories", "followers"]):
            author = link_text
            break

    if author == "Unbekannt":
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            author = str(meta_author["content"]).strip()

    if author == "Unbekannt":
        # Suche nach Klassen mit "author"
        author_elem = soup.find(class_=re.compile(r"\bauthor\b", re.I))
        if author_elem:
            cleaned_author = author_elem.get_text(strip=True)
            if cleaned_author:
                author = cleaned_author

    return title, author


def detect_total_pages(soup: BeautifulSoup, html: str) -> int:
    """
    Ermittelt die Gesamtzahl der Seiten einer Geschichte.
    Nutzt mehrere Heuristiken:
    1. Input-Feld der Paginierung: <input name="page" max="17">
    2. Paginierungs-Links mit ?page=X
    3. Textmuster 'Seite 1 von X' oder 'Page 1 of X'
    """
    detected_pages = [1]

    # Heuristik 1: input-Feld mit max-Attribut
    page_input = soup.find("input", attrs={"name": "page", "max": True})
    if page_input and page_input.get("max"):
        try:
            detected_pages.append(int(str(page_input["max"])))
        except ValueError:
            pass

    # Heuristik 2: Links mit ?page=X
    for a in soup.find_all("a", href=re.compile(r"[?&]page=(\d+)")):
        m = re.search(r"[?&]page=(\d+)", str(a.get("href", "")))
        if m:
            detected_pages.append(int(m.group(1)))

    # Heuristik 3: Textuelle Paginierungsanzeige 'Seite 1 von 17'
    for match in re.finditer(r"(?:Seite|Page)\s*\d+\s*(?:von|of)\s*(\d+)", html, re.I):
        try:
            detected_pages.append(int(match.group(1)))
        except ValueError:
            pass

    return max(detected_pages)


def extract_story_paragraphs(html: str) -> list[str]:
    """
    Extrahiert die reinen Textabsätze einer einzelnen Seite als saubere HTML-<p>-Tags.
    Entfernt Header, Fußzeilen, Paginierung, Kommentare, Scripts und Werbung.
    """
    soup = BeautifulSoup(html, "lxml")

    # 1. Unnötige Tags und störende UI-Elemente entfernen
    unwanted_tags = [
        "script", "style", "noscript", "nav", "header", "footer",
        "form", "aside", "button", "svg", "iframe"
    ]
    for tag in soup.find_all(unwanted_tags):
        tag.decompose()

    unwanted_classes = re.compile(
        r"(?:comment|rating|vote|share|ad|banner|promo|breadcrumb|pagination|sidebar|userpic)",
        re.I
    )
    for tag in soup.find_all(class_=unwanted_classes):
        tag.decompose()

    # 2. Haupttext-Container lokalisieren
    article = soup.find("article") or soup

    # Priorität A: Modernes Literotica Layout (_introduction-wrap / _introduction__text)
    story_container = article.find(class_=re.compile(r"_introduction(?:-wrap|__text)", re.I))

    # Priorität B: Älteres / klassisches Literotica Layout (aa_ht / b-story-body-x)
    if not story_container:
        story_container = article.find(class_=re.compile(r"(?:aa_ht|b-story-body-x)", re.I))

    # Priorität C: Container mit den meisten Absätzen (<p>)
    if not story_container:
        candidates = []
        for div in article.find_all("div"):
            p_list = div.find_all("p", recursive=False)
            if p_list:
                candidates.append((div, len(p_list)))
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            story_container = candidates[0][0]

    # 3. Absätze formatieren und bereinigen
    paragraphs: list[str] = []
    if story_container:
        p_elements = story_container.find_all("p")
        for p in p_elements:
            # Entferne alle Literotica-Attribute wie data-hk, class, style
            p.attrs = {}

            # Inline-Tags bereinigen: Erlaube nur sichere Formatierungs-Tags
            for child in p.find_all(True):
                if child.name in SAFE_INLINE_TAGS:
                    child.attrs = {}
                else:
                    child.unwrap()

            text = p.get_text(strip=True)
            if not text:
                continue

            # Boilerplate, Werbung und unerwünschte Phrasen herausfiltern
            if any(phrase.lower() in text.lower() for phrase in UNWANTED_PHRASES):
                continue

            paragraphs.append(str(p))

    # Fallback: Falls keine <p>-Tags existieren, aber Fließtext mit <br> vorliegt
    if not paragraphs and story_container:
        raw_text = story_container.get_text()
        blocks = [b.strip() for b in raw_text.split("\n") if b.strip()]
        for block in blocks:
            if not any(phrase.lower() in block.lower() for phrase in UNWANTED_PHRASES):
                paragraphs.append(f"<p>{block}</p>")

    return paragraphs


async def _fetch_single_page(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    page_num: int,
    base_url: str
) -> tuple[int, Optional[str], Optional[str]]:
    """
    Holt eine Unterseite ab und gibt (page_num, html_content, error_msg) zurück.
    """
    url = f"{base_url}?page={page_num}" if page_num > 1 else base_url
    async with sem:
        try:
            # Kleines kooperatives Delay zur Entlastung des Zielservers
            await asyncio.sleep(0.05)
            response = await client.get(url)
            if response.status_code == 200:
                return page_num, response.text, None
            else:
                return page_num, None, f"HTTP Status {response.status_code}"
        except httpx.HTTPError as exc:
            return page_num, None, str(exc)
        except Exception as exc:
            return page_num, None, f"Unerwarteter Fehler: {exc}"


async def scrape_story(
    base_url: str,
    client: Optional[httpx.AsyncClient] = None,
    max_concurrent_pages: int = 4
) -> dict:
    """
    Hauptfunktion: Extrahiert eine vollständige Geschichte von german.literotica.com.
    
    Rückgabe-Dictionary:
    {
        "title": str,
        "author": str,
        "url": str,
        "total_pages": int,
        "content_html": str,
        "error": Optional[str],
    }
    """
    clean_url = clean_base_url(base_url)
    logger.info(f"Starte Scraping für: {clean_url}")

    own_client = False
    if client is None:
        client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=25.0
        )
        own_client = True

    try:
        # 1. Seite 1 abrufen
        try:
            resp = await client.get(clean_url)
            if resp.status_code != 200:
                error_msg = f"Fehler beim Laden von Seite 1: HTTP {resp.status_code}"
                logger.error(f"{error_msg} ({clean_url})")
                return {
                    "title": f"Abruffehler: {clean_url}",
                    "author": "Unbekannt",
                    "url": clean_url,
                    "total_pages": 0,
                    "content_html": f"<p class='error'>{error_msg}</p>",
                    "error": error_msg,
                }
        except Exception as exc:
            error_msg = f"Netzwerkfehler beim Aufruf von Seite 1: {exc}"
            logger.error(f"{error_msg} ({clean_url})")
            return {
                "title": f"Abruffehler: {clean_url}",
                "author": "Unbekannt",
                "url": clean_url,
                "total_pages": 0,
                "content_html": f"<p class='error'>{error_msg}</p>",
                "error": error_msg,
            }

        page_1_html = resp.text
        page_1_soup = BeautifulSoup(page_1_html, "lxml")

        # 2. Metadaten extrahieren
        title, author = extract_metadata(page_1_soup, clean_url)
        total_pages = detect_total_pages(page_1_soup, page_1_html)
        logger.info(f"Metadaten gefunden: Titel='{title}', Autor='{author}', Seiten={total_pages}")

        # 3. Absätze von Seite 1 extrahieren
        page_paragraphs_dict: dict[int, list[str]] = {}
        page_paragraphs_dict[1] = extract_story_paragraphs(page_1_html)

        # 4. Falls mehrseitig: Alle Folgeseiten parallel mit Semaphore abrufen
        if total_pages > 1:
            sem = asyncio.Semaphore(max_concurrent_pages)
            tasks = [
                _fetch_single_page(client, sem, page_num, clean_url)
                for page_num in range(2, total_pages + 1)
            ]
            results = await asyncio.gather(*tasks)

            for page_num, page_html, err in results:
                if err:
                    logger.warning(f"Seite {page_num} von {clean_url} fehlgeschlagen: {err}")
                    page_paragraphs_dict[page_num] = [
                        f"<p><em>[Hinweis: Seite {page_num} konnte nicht geladen werden ({err})]</em></p>"
                    ]
                elif page_html:
                    ps = extract_story_paragraphs(page_html)
                    page_paragraphs_dict[page_num] = ps

        # 5. Alle Absätze in exakter Seitenreihenfolge zusammenführen
        all_paragraphs: list[str] = []
        for p_idx in range(1, total_pages + 1):
            if p_idx in page_paragraphs_dict:
                all_paragraphs.extend(page_paragraphs_dict[p_idx])

        # Falls keine Absätze gefunden wurden (z.B. unerwartete Seitenstruktur)
        if not all_paragraphs:
            content_html = "<p><em>[Kein Story-Text auf den Seiten gefunden]</em></p>"
        else:
            content_html = "\n".join(all_paragraphs)

        return {
            "title": title,
            "author": author,
            "url": clean_url,
            "total_pages": total_pages,
            "content_html": content_html,
            "error": None,
        }

    except Exception as exc:
        error_msg = f"Unerwarteter Fehler beim Scrapen: {exc}"
        logger.exception(error_msg)
        return {
            "title": f"Fehler: {clean_url}",
            "author": "Unbekannt",
            "url": clean_url,
            "total_pages": 0,
            "content_html": f"<p class='error'>{error_msg}</p>",
            "error": error_msg,
        }
    finally:
        if own_client:
            await client.aclose()


def extract_series_story_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """
    Extrahiert alle Geschichten-URLs aus dem HTML einer Serienseite.
    """
    urls: list[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        # Normalisiere URL, entferne Anker und Query
        norm = urljoin(base_url, href.split("#", 1)[0].split("?", 1)[0].strip())
        parsed = urlparse(norm)
        if parsed.path.startswith("/s/"):
            if norm not in seen:
                seen.add(norm)
                urls.append(norm)
    return urls


async def fetch_series_info(
    series_url: str,
    client: Optional[httpx.AsyncClient] = None
) -> dict:
    """
    Extrahiert Metadaten (Titel, Autor) und alle Story-Links aus einer Serien-URL.
    Unterstützt auch mehrseitige Serienübersichten.
    
    Rückgabe-Dictionary:
    {
        "title": str,
        "author": str,
        "story_urls": list[str],
        "error": Optional[str],
    }
    """
    clean_url = series_url.strip()
    logger.info(f"Löse Serie auf: {clean_url}")

    own_client = False
    if client is None:
        client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=25.0
        )
        own_client = True

    try:
        resp = await client.get(clean_url)
        if resp.status_code != 200:
            err = f"Serienseite konnte nicht geladen werden (HTTP {resp.status_code})"
            logger.error(err)
            return {"title": "Unbekannte Serie", "author": "Unbekannt", "story_urls": [], "error": err}

        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        # 1. Serientitel
        title = ""
        h1 = soup.find("h1")
        if h1:
            raw_title = h1.get_text()
            title = re.sub(r"<!--.*?-->", "", raw_title).strip()

        if not title:
            meta_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
            if meta_title and meta_title.get("content"):
                title = str(meta_title["content"]).strip()
                title = re.sub(r"\s*-\s*Story Series.*$", "", title, flags=re.I).strip()
                title = re.sub(r"\s*-\s*Literotica(?:\.com)?.*$", "", title, flags=re.I).strip()

        if not title:
            path_slug = urlparse(clean_url).path.split("/")[-1]
            title = path_slug.replace("-", " ").replace("_", " ").title() if path_slug else "Literotica Serie"

        # 2. Serienautor
        author = "Unbekannt"
        for a in soup.find_all("a", href=re.compile(r"/(?:authors|members)/")):
            link_text = a.get_text(strip=True)
            if link_text and not any(kw in link_text.lower() for kw in ["geschichten", "anhänger", "stories", "followers"]):
                author = link_text
                break

        if author == "Unbekannt":
            meta_author = soup.find("meta", attrs={"name": "author"})
            if meta_author and meta_author.get("content"):
                author = str(meta_author["content"]).strip()

        # 3. Geschichten der Serie extrahieren
        story_urls = extract_series_story_links(soup, str(resp.url))

        # 4. Prüfen ob die Serie selbst paginiert ist (mehr als 1 Seite an Story-Links)
        series_pages = detect_total_pages(soup, html)
        if series_pages > 1:
            logger.info(f"Serie umfasst {series_pages} Übersichtsseiten. Rufe Folgeseiten ab...")
            for page in range(2, series_pages + 1):
                page_url = f"{clean_url}?page={page}"
                try:
                    p_resp = await client.get(page_url)
                    if p_resp.status_code == 200:
                        p_soup = BeautifulSoup(p_resp.text, "lxml")
                        more_urls = extract_series_story_links(p_soup, str(p_resp.url))
                        for u in more_urls:
                            if u not in story_urls:
                                story_urls.append(u)
                except Exception as exc:
                    logger.warning(f"Serien-Paginierungsseite {page} fehlgeschlagen: {exc}")

        logger.info(f"Serie '{title}' von '{author}': {len(story_urls)} Geschichte(n) gefunden")
        return {
            "title": title,
            "author": author,
            "story_urls": story_urls,
            "error": None if story_urls else "Keine Geschichten in der Serie gefunden",
        }

    except Exception as exc:
        err = f"Fehler beim Abruf der Serie {clean_url}: {exc}"
        logger.exception(err)
        return {"title": "Fehler Serie", "author": "Unbekannt", "story_urls": [], "error": err}
    finally:
        if own_client:
            await client.aclose()


def scrape_story_sync(base_url: str) -> dict:
    """
    Synchroner Wrapper für scrape_story.
    """
    return asyncio.run(scrape_story(base_url))


