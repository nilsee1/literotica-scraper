"""
EPUB Builder Module
Erstellt ein standardkonformes EPUB3-Dokument aus gescrapten Literotica-Geschichten
mit vollständigen Metadaten, strukturierter Kapitel-Hierarchie, Inhaltsverzeichnis (TOC)
und typografisch optimiertem Stylesheet.
"""

from datetime import date
import logging
import os
import re
import tempfile
from typing import Any, Optional
import uuid

import ebooklib
from ebooklib import epub

logger = logging.getLogger("epub_builder")

EPUB_STYLESHEET = """
@charset "utf-8";

body {
    font-family: "Georgia", "Cambria", "Times New Roman", serif;
    font-size: 1.05em;
    line-height: 1.65;
    color: #1a1a1a;
    margin: 5% 7%;
    padding: 0;
}

h1 {
    font-size: 1.8em;
    font-weight: 700;
    line-height: 1.3;
    margin-top: 1.2em;
    margin-bottom: 0.5em;
    color: #111827;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 1.4em;
    font-weight: 600;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    color: #374151;
}

p {
    margin-top: 0;
    margin-bottom: 0.85em;
    text-align: justify;
    text-justify: inter-word;
    hyphens: auto;
}

.chapter-meta {
    font-size: 0.9em;
    color: #4b5563;
    background-color: #f9fafb;
    border-left: 3px solid #6366f1;
    padding: 0.5em 0.8em;
    margin-bottom: 1.8em;
    border-radius: 2px;
}

.chapter-meta a {
    color: #4f46e5;
    text-decoration: underline;
}

.title-page {
    text-align: center;
    margin-top: 15%;
    margin-bottom: 15%;
}

.title-page h1 {
    font-size: 2.2em;
    border: none;
    margin-bottom: 0.3em;
}

.title-page .subtitle {
    font-size: 1.2em;
    color: #4b5563;
    margin-bottom: 2em;
}

.title-page .meta {
    font-size: 0.95em;
    color: #6b7280;
    line-height: 1.8;
}

.error-notice {
    background-color: #fef2f2;
    border: 1px solid #f87171;
    border-left: 4px solid #ef4444;
    color: #991b1b;
    padding: 0.8em 1em;
    border-radius: 4px;
    margin: 1.5em 0;
}
"""


def sanitize_filename_component(value: str) -> str:
    """
    Entfernt ungültige Dateisystem-Zeichen und bereinigt Whitespace.
    """
    clean = re.sub(r'[\\/*?:"<>|]', "", value)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def sanitize_title_for_filename(title: str) -> str:
    """
    Kompatibilitäts-Helper für bereinigte Namen.
    """
    return sanitize_filename_component(title) or "Literotica_Sammlung"


def build_epub_filename(author: str, title: str) -> str:
    """
    Erstellt den geforderten Dateinamen im Format: 'Autor - Titel.epub'
    """
    safe_author = sanitize_filename_component(author) or "Literotica Autoren"
    safe_title = sanitize_filename_component(title) or "Literotica Sammlung"
    return f"{safe_author} - {safe_title}.epub"


def build_epub(
    stories: list[dict[str, Any]],
    book_title: str = "",
    book_author: str = "",
    book_year: Optional[int | str] = None
) -> bytes:
    """
    Baut ein valides EPUB3-Dokument aus den übergebenen Story-Dictionaries.
    
    Jede Story wird zu einem eigenständigen Kapitel im EPUB.
    Gibt den Inhalt der .epub-Datei als Bytes zurück.
    """
    current_date = date.today()
    today_str = current_date.isoformat()

    if not book_year or str(book_year).strip() == "":
        book_year = current_date.year
    else:
        book_year = str(book_year).strip()

    if not book_title or not book_title.strip():
        book_title = f"Literotica Sammlung - {today_str}"
    else:
        book_title = book_title.strip()

    if not book_author or not book_author.strip():
        book_author = "Literotica Autoren / Kompilation"
    else:
        book_author = book_author.strip()

    logger.info(f"Erstelle EPUB: '{book_title}' von '{book_author}' ({book_year}) mit {len(stories)} Kapiteln")

    # 1. EpubBook initialisieren & Metadaten setzen
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(book_title)
    book.set_language("de")
    book.add_author(book_author)
    book.add_metadata("DC", "date", str(book_year))

    # 2. Stylesheet hinzufügen
    style_item = epub.EpubItem(
        uid="style_nav",
        file_name="style/style.css",
        media_type="text/css",
        content=EPUB_STYLESHEET
    )
    book.add_item(style_item)

    chapters: list[epub.EpubHtml] = []
    toc_links: list[epub.Link] = []

    # 3. Titelseite erstellen
    title_page = epub.EpubHtml(
        title="Titel",
        file_name="titlepage.xhtml",
        lang="de"
    )
    title_page.add_item(style_item)
    title_page.content = f"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="de" lang="de">
<head>
    <title>{book_title}</title>
    <link rel="stylesheet" href="style/style.css" type="text/css"/>
</head>
<body>
    <div class="title-page">
        <h1>{book_title}</h1>
        <p class="subtitle">Kuratierte Erotische Kurzgeschichten</p>
        <div class="meta">
            <p><strong>Autor / Herausgeber:</strong> {book_author}</p>
            <p><strong>Jahr:</strong> {book_year}</p>
            <p><strong>Erstellt am:</strong> {today_str}</p>
            <p><strong>Enthaltene Geschichten:</strong> {len(stories)}</p>
            <p><strong>Quelle:</strong> <a href="https://german.literotica.com">german.literotica.com</a></p>
        </div>
    </div>
</body>
</html>"""
    book.add_item(title_page)

    # 4. Einzelne Kapitel erstellen
    for idx, story in enumerate(stories, start=1):
        st_title = story.get("title") or f"Kapitel {idx}"
        st_author = story.get("author") or "Unbekannt"
        st_url = story.get("url") or ""
        st_pages = story.get("total_pages", 1)
        st_content = story.get("content_html") or ""
        st_error = story.get("error")

        file_name = f"chapter_{idx:03d}.xhtml"
        chapter = epub.EpubHtml(
            title=st_title,
            file_name=file_name,
            lang="de"
        )
        chapter.add_item(style_item)

        # Fehlerbehandlung: Platzhalter-Meldung falls Abruf fehlschlug
        error_html = ""
        if st_error:
            error_html = f"""
            <div class="error-notice">
                <p><strong>Hinweis zum Abruf:</strong> Beim Laden dieser Geschichte ist ein Fehler aufgetreten ({st_error}).</p>
            </div>
            """

        chapter_body = f"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="de" lang="de">
<head>
    <title>{st_title}</title>
    <link rel="stylesheet" href="style/style.css" type="text/css"/>
</head>
<body>
    <h1>{st_title}</h1>
    <p class="chapter-meta"><em>Autor: {st_author} | Quelle: <a href="{st_url}">{st_url}</a></em></p>
    {error_html}
    <div class="story-content">
        {st_content}
    </div>
</body>
</html>"""
        chapter.content = chapter_body
        book.add_item(chapter)
        chapters.append(chapter)
        toc_links.append(epub.Link(file_name, st_title, f"chap_{idx:03d}"))

    # 5. Inhaltsverzeichnis (TOC) konfigurieren
    book.toc = tuple(toc_links)

    # 6. Navigation (NCX für EPUB2-Kompatibilität & NAV für EPUB3)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # 7. Spine aufbauen
    book.spine = ["nav", title_page] + chapters

    # 8. EPUB als Bytes generieren
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as temp_epub:
        temp_path = temp_epub.name

    try:
        epub.write_epub(temp_path, book, {})
        with open(temp_path, "rb") as f:
            epub_data = f.read()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    logger.info(f"EPUB erfolgreich generiert ({len(epub_data)} Bytes)")
    return epub_data

