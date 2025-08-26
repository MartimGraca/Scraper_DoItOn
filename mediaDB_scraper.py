import os
import time
import logging
import unicodedata
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse, urlencode

import requests
from bs4 import BeautifulSoup
import feedparser

# Configuração de logs
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("media_db_scraper")

# Timeouts e limites
REQ_TIMEOUT = float(os.getenv("SCRAPER_REQ_TIMEOUT", "8.0"))
MAX_ITEMS_PER_SITE = int(os.getenv("SCRAPER_MAX_ITEMS_PER_SITE", "8"))
SLEEP_BETWEEN_SITES = float(os.getenv("SCRAPER_SLEEP_BETWEEN_SITES", "0.2"))

# Caminhos de feed comuns
COMMON_FEED_PATHS = [
    "/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml",
    "/feeds/posts/default?alt=rss"  # Blogger
]

# Rotas de pesquisa comuns
SEARCH_PATTERNS = [
    # WordPress
    lambda base, kw: f"{base}/?{urlencode({'s': kw})}",
    # Genéricas
    lambda base, kw: f"{base}/search?{urlencode({'q': kw})}",
    lambda base, kw: f"{base}/pesquisa?{urlencode({'q': kw})}",
    lambda base, kw: f"{base}/procurar?{urlencode({'q': kw})}",
    lambda base, kw: f"{base}/busca?{urlencode({'q': kw})}",
]

HEADERS = {
    "User-Agent": os.getenv("SCRAPER_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36")
}

def _norm(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return s.lower().strip()

def _contains(text: str, keyword: str) -> bool:
    return _norm(keyword) in _norm(text)

def get_site_root(url: str) -> str:
    """Garante root sem path e sem trailing slash."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    return root.rstrip("/")

def safe_get(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
        if 200 <= r.status_code < 300:
            return r
        return None
    except Exception as e:
        logger.debug(f"GET falhou {url}: {e}")
        return None

def discover_feeds(base_url: str) -> List[str]:
    feeds = []
    root = get_site_root(base_url)
    if not root:
        return feeds

    # 1) Procurar <link rel="alternate" type="application/rss+xml">
    resp = safe_get(root)
    if resp and resp.text:
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
            t = (link.get("type") or "").lower()
            if "rss" in t or "atom" in t or "xml" in t:
                href = link.get("href")
                if href:
                    feeds.append(urljoin(root + "/", href))

    # 2) Testar caminhos comuns
    for path in COMMON_FEED_PATHS:
        feed_url = root + path
        if feed_url in feeds:
            continue
        r = safe_get(feed_url)
        if r and ("<rss" in r.text or "<feed" in r.text or "<channel" in r.text):
            feeds.append(feed_url)

    # dedup simples
    seen = set()
    out = []
    for f in feeds:
        if f not in seen:
            seen.add(f)
            out.append(f)
    logger.debug(f"Feeds para {root}: {out}")
    return out

def parse_feed(feed_url: str, max_items: int) -> List[Dict]:
    d = feedparser.parse(feed_url)
    items = []
    for e in d.entries[:max_items * 2]:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        published = (e.get("published") or e.get("updated") or "").strip()
        summary = (e.get("summary") or "")
        if not link:
            continue
        items.append({
            "title": title,
            "url": link,
            "published": published,
            "summary": BeautifulSoup(summary, "html.parser").get_text(" ").strip()
        })
    return items

def search_site_pages(base_url: str, keyword: str, max_items: int) -> List[Dict]:
    """Fallback de pesquisa via rotas comuns. Extrai anchors e filtra por keyword no texto."""
    results: List[Dict] = []
    root = get_site_root(base_url)
    if not root:
        return results
    tried = set()
    for builder in SEARCH_PATTERNS:
        url = builder(root, keyword)
        if url in tried:
            continue
        tried.add(url)
        r = safe_get(url)
        if not r or not r.text:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        anchors = soup.find_all("a")
        for a in anchors:
            href = a.get("href")
            text = a.get_text(" ").strip()
            if not href or not text or len(text) < 12:
                continue
            full = urljoin(root + "/", href)
            # manter no mesmo domínio
            if urlparse(full).netloc != urlparse(root).netloc:
                continue
            if _contains(text, keyword):
                results.append({"title": text, "url": full, "published": "", "summary": ""})
        if results:
            break
    # dedup e limitar
    dedup: Dict[str, Dict] = {}
    for it in results:
        dedup[it["url"]] = it
    out = list(dedup.values())[:max_items]
    return out

def scrape_media_site(media: Dict, keyword: str, max_items_per_site: int = None) -> List[Dict]:
    """
    media: {"id": int, "nome": str, "url": str}
    Retorna lista: {"title","url","published","source","media_id","media_nome"}
    """
    if max_items_per_site is None:
        max_items_per_site = MAX_ITEMS_PER_SITE

    base_url = media.get("url") or ""
    nome = media.get("nome") or ""
    if not base_url:
        return []

    # 1) Tenta feeds
    try:
        feeds = discover_feeds(base_url)
    except Exception as e:
        logger.debug(f"[{nome}] discover_feeds falhou: {e}")
        feeds = []

    collected: List[Dict] = []
    for f in feeds:
        try:
            items = parse_feed(f, max_items_per_site)
            for it in items:
                if _contains(f"{it['title']} {it['summary']}", keyword):
                    collected.append({
                        "title": it["title"],
                        "url": it["url"],
                        "published": it["published"],
                        "source": "rss",
                        "media_id": media.get("id"),
                        "media_nome": nome
                    })
            if collected:
                break
        except Exception as e:
            logger.debug(f"[{nome}] parse_feed falhou ({f}): {e}")

    # 2) Fallback pesquisa
    if not collected:
        try:
            items = search_site_pages(base_url, keyword, max_items_per_site)
            for it in items:
                collected.append({
                    "title": it["title"],
                    "url": it["url"],
                    "published": it["published"],
                    "source": "search",
                    "media_id": media.get("id"),
                    "media_nome": nome
                })
        except Exception as e:
            logger.debug(f"[{nome}] search_site_pages falhou: {e}")

    # dedup e limitar
    dedup: Dict[str, Dict] = {}
    for it in collected:
        dedup[it["url"]] = it
    final = list(dedup.values())[:max_items_per_site]
    logger.info(f"[{nome}] resultados: {len(final)} (keyword='{keyword}')")
    return final

def scrape_sites(media_list: List[Dict], keyword: str, max_items_per_site: int = None, sleep_between_sites: float = None) -> List[Dict]:
    """Corre scraping em todos os sites da lista e agrega resultados."""
    if max_items_per_site is None:
        max_items_per_site = MAX_ITEMS_PER_SITE
    if sleep_between_sites is None:
        sleep_between_sites = SLEEP_BETWEEN_SITES

    aggregated: List[Dict] = []
    logger.info(f"A processar {len(media_list)} sites...")
    for m in media_list:
        try:
            items = scrape_media_site(m, keyword, max_items_per_site)
            aggregated.extend(items)
        except Exception as e:
            logger.debug(f"Erro no site '{m.get('nome') or m.get('url')}': {e}")
        time.sleep(sleep_between_sites)
    # dedup final
    dedup: Dict[str, Dict] = {}
    for it in aggregated:
        dedup[it["url"]] = it
    final = list(dedup.values())
    logger.info(f"Total resultados agregados: {len(final)}")
    return final