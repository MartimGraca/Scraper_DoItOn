import re
import os
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("mediaDB_scraper")

DEFAULT_UA = os.getenv("SCRAPER_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36")
REQ_TIMEOUT = float(os.getenv("SCRAPER_REQ_TIMEOUT", "6.0"))

def healthcheck() -> str:
    return "ok"

def parse_keywords(keywords_raw: str) -> List[str]:
    if not keywords_raw:
        return []
    # separa por vírgula/linhas
    parts = [p.strip() for p in re.split(r"[,\n]+", keywords_raw) if p.strip()]
    return parts

def _like_clause_for_keywords(keywords: List[str], fields: List[str], match_all: bool, params_out: List[Any]) -> str:
    if not keywords or not fields:
        return ""
    subclauses: List[str] = []
    for kw in keywords:
        ors: List[str] = []
        for f in fields:
            ors.append(f"{f} LIKE %s")
            params_out.append(f"%{kw}%")
        subclauses.append("(" + " OR ".join(ors) + ")")
    return (" AND ".join(subclauses)) if match_all else (" OR ".join(subclauses))

def search_media(
    cursor,
    keywords_raw: str,
    fields: List[str],
    match_all: bool,
    tipologia_filter: Optional[str],
    segmento_filter: Optional[str],
    tier_filter: Optional[int],
    limit_results: int = 200,
) -> List[Dict[str, Any]]:
    """
    Pesquisa diretamente na tabela 'media' com LIKEs e filtros.
    fields subset de ["nome","url","tipologia","segmento"]
    match_all: True => todas as palavras, False => qualquer palavra
    """
    keywords = parse_keywords(keywords_raw)
    campos = fields or ["nome", "url"]

    where_parts: List[str] = []
    params: List[Any] = []

    like_clause = _like_clause_for_keywords(keywords, campos, match_all, params)
    if like_clause:
        where_parts.append(f"({like_clause})")

    if tipologia_filter and tipologia_filter != "Qualquer":
        where_parts.append("tipologia = %s")
        params.append(tipologia_filter)
    if segmento_filter and segmento_filter != "Qualquer":
        where_parts.append("segmento = %s")
        params.append(segmento_filter)
    if tier_filter not in (None, "Qualquer", ""):
        try:
            params.append(int(tier_filter))
            where_parts.append("tier = %s")
        except Exception:
            pass

    sql = """
        SELECT id, nome, url, cliente_id, tipologia, segmento, tier
        FROM media
    """
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(int(limit_results))

    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": r[0],
            "nome": r[1],
            "url": r[2],
            "cliente_id": r[3],
            "tipologia": r[4],
            "segmento": r[5],
            "tier": r[6],
        })
    return out

def _fetch_html(url: str, timeout: float, ua: str) -> Optional[str]:
    if not url:
        return None
    headers = {"User-Agent": ua or DEFAULT_UA}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if 200 <= resp.status_code < 300 and resp.text:
            return resp.text
    except Exception:
        return None
    return None

def _guess_favicon(base_url: str, soup: BeautifulSoup) -> Optional[str]:
    for rel in ["icon", "shortcut icon", "apple-touch-icon", "mask-icon"]:
        link = soup.find("link", rel=lambda v: v and rel in v.lower())
        if link and link.get("href"):
            return urljoin(base_url, link["href"])
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return urljoin(root + "/", "/favicon.ico")

def _get_og_image(base_url: str, soup: BeautifulSoup) -> Optional[str]:
    og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    if og and og.get("content"):
        return urljoin(base_url, og["content"])
    tw = soup.find("meta", property="twitter:image") or soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return urljoin(base_url, tw["content"])
    img = soup.find("img", src=True)
    if img:
        return urljoin(base_url, img["src"])
    return None

def enrich_previews(items: List[Dict[str, Any]], timeout: float = None, user_agent: str = None) -> List[Dict[str, Any]]:
    """
    Para cada item com 'url', tenta obter imagem OG e favicon para mostrar um card.
    Não falha o fluxo se não conseguir (campos ficam None).
    """
    if timeout is None:
        timeout = REQ_TIMEOUT
    ua = user_agent or DEFAULT_UA

    enriched: List[Dict[str, Any]] = []
    for it in items:
        url = it.get("url") or ""
        og_image = None
        favicon = None
        if url:
            html_text = _fetch_html(url, timeout, ua)
            if html_text:
                try:
                    soup = BeautifulSoup(html_text, "html.parser")
                    og_image = _get_og_image(url, soup)
                    favicon = _guess_favicon(url, soup)
                except Exception:
                    pass
        new = dict(it)
        new["og_image"] = og_image
        new["favicon"] = favicon
        enriched.append(new)
    return enriched