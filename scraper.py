import asyncio
import gc
import logging
import os
import sys
import traceback
from typing import Optional, Tuple
from urllib.parse import urlparse, urljoin, urldefrag

from dotenv import load_dotenv
from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import async_playwright

load_dotenv()

# ========= CONFIG =========
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "60"))       # limite de links recolhidos na página de resultados
MAX_TOP_LINKS = int(os.getenv("MAX_TOP_LINKS", "8"))          # máximo de artigos a abrir por keyword
NAV_TIMEOUT = int(os.getenv("NAV_TIMEOUT_MS", "20000"))       # timeout de navegação
ACT_TIMEOUT = int(os.getenv("ACTION_TIMEOUT_MS", "9000"))     # timeout de ações (click/fill/etc)
BLOCK_IMAGES = os.getenv("BLOCK_IMAGES", "1") == "1"
BLOCK_MEDIA = os.getenv("BLOCK_MEDIA", "1") == "1"
BLOCK_FONTS = os.getenv("BLOCK_FONTS", "1") == "1"
BLOCK_ADS = os.getenv("BLOCK_ADS", "1") == "1"
USE_MOBILE = os.getenv("USE_MOBILE", "1") == "1"
ALLOW_NO_MATCH = os.getenv("ALLOW_NO_MATCH", "1") == "1"      # devolve resultados mesmo sem match exato no conteúdo
SHOW_LINK_REASONS = os.getenv("SHOW_LINK_REASONS", "0") == "1"  # logs dos motivos de exclusão de links

# ========= LOGGING =========
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper_log.txt", mode="w")
    ]
)
logger = logging.getLogger("scraper")

LOGIN_EMAIL = os.getenv("LOGIN_EMAIL", "")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")

BLOCKED_URL_HINTS = [
    "login", "signin", "signup", "auth",
    "contact", "contato", "sobre", "about",
    "privacidade", "privacy", "termos", "terms", "cookies",
    "condicoes", "condições", "ajuda", "help", "support",
    "faq", "perguntas", "utilizacao", "utilização",
    "politica", "política", "regulamento", "legal", "copyright"
]
NEWS_PATH_HINTS = [
    "noticia", "notícias", "noticias", "artigo", "artigos",
    "atualidade", "actualidade", "mundo", "sociedade",
    "economia", "cultura", "desporto", "tecnologia",
    "saude", "saúde", "portugal"
]
EXCLUDED_SUBDOMAINS = ["ajuda", "help", "support", "login", "auth", "conta", "store", "shop", "blog"]

AD_HOST_HINTS = [
    "doubleclick.net", "googlesyndication.com", "googletagmanager.com", "google-analytics.com",
    "facebook.net", "twitter.com/i", "scorecardresearch.com", "criteo.com", "taboola.com",
    "outbrain.com", "cloudfront.net", "adservice.google.com", "hotjar.com"
]


def get_site_name(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    parts = domain.split('.')
    subdominios_ignorados = ['www', 'news']
    filtered_parts = [part for part in parts if part not in subdominios_ignorados]
    if len(filtered_parts) > 1:
        site_name = filtered_parts[-2].capitalize()
    else:
        site_name = filtered_parts[0].capitalize()
    return site_name


def get_base_domain(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def normalize_url(base_url: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    full = urljoin(base_url, href)
    full, _ = urldefrag(full)
    if not full.startswith(("http://", "https://")):
        return None
    return full


def host_allowed(candidate_host: str, base_host: str) -> bool:
    base_root = get_base_domain(base_host)
    if candidate_host == base_host or candidate_host.endswith("." + base_root):
        sub_parts = candidate_host.replace("." + base_root, "")
        sub = sub_parts.split(".")[-1] if sub_parts else ""
        if sub and sub.lower() in EXCLUDED_SUBDOMAINS:
            return False
        return True
    return False


def link_filter_reason(base_host: str, url: str, text: str) -> Tuple[bool, str]:
    u = url.lower()
    t = (text or "").lower().strip()

    if any(b in u for b in BLOCKED_URL_HINTS):
        return False, "blocked_by_url_hint"
    if any(b in t for b in BLOCKED_URL_HINTS):
        return False, "blocked_by_text_hint"

    if len(t) < 12:
        return False, "text_too_short"

    cand_host = urlparse(url).netloc
    if not host_allowed(cand_host, base_host):
        return False, "other_domain"

    # Se tiver pista de notícia, ótimo
    if any(h in u for h in NEWS_PATH_HINTS) or any(h in t for h in NEWS_PATH_HINTS):
        return True, "news_hint"

    # Caso não tenha pistas, ainda aceitamos
    return True, "generic_ok"


async def clicar_carregar_mais(page, max_clicks: int = 2):
    textos = ["Mais notícias", "Ver mais", "Mostrar mais", "Carregar mais", "Mais artigos"]
    clicks = 0
    for _ in range(max_clicks):
        clicked = False
        for tx in textos:
            try:
                btn = await page.query_selector(f'button:has-text("{tx}"), a:has-text("{tx}")')
                if btn:
                    try:
                        await btn.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    await btn.click(timeout=1500)
                    await page.wait_for_timeout(800)
                    clicks += 1
                    clicked = True
                    logger.info(f"Clique em botão de expandir: {tx}")
                    break
            except Exception:
                continue
        if not clicked:
            break
    logger.info(f"Expandir listas concluído. Cliques: {clicks}")


async def aceitar_cookies(page):
    await page.wait_for_timeout(800)
    cookie_selectors = [
        'button[aria-label*="aceitar" i]',
        'button:has-text("Aceitar")',
        'button:has-text("Accept")',
        'button:has-text("Concordo")',
        'button[aria-label*="concordo" i]',
        'button[aria-label*="Consentir" i]',
        'button:has-text("Consentir")',
        'div[role="dialog"] button:has-text("Aceitar")',
        'div[class*="cookie"] button:has-text("Aceitar")',
        'button#onetrust-accept-btn-handler',
        'button[title="Aceitar todos"]',
        'button[mode="primary"]',
    ]
    for selector in cookie_selectors:
        try:
            btn = await page.query_selector(selector)
            if btn:
                try:
                    await btn.scroll_into_view_if_needed()
                except Exception:
                    pass
                try:
                    await btn.click(timeout=800)
                except Exception:
                    try:
                        await page.evaluate("(el) => el.click()", btn)
                    except Exception:
                        continue
                logger.info(f"Cookies aceites via seletor: {selector}")
                return
        except Exception:
            continue
    # iframes
    try:
        for frame in page.frames:
            for selector in cookie_selectors:
                try:
                    btn = await frame.query_selector(selector)
                    if btn:
                        await btn.click(timeout=800)
                        logger.info(f"Cookies aceites num iframe: {selector}")
                        return
                except Exception:
                    continue
    except Exception:
        pass
    logger.info("Nenhum popup de cookies encontrado/necessário.")


async def encontrar_e_preencher_pesquisa(page, keyword):
    logger.info("A procurar campo de pesquisa...")
    input_seletor = (
        'input[type="search"], input[type="text"], '
        'input[placeholder*="pesquisar" i], input[placeholder*="search" i], '
        'input[name*="search" i], input[id*="search" i], input[class*="search" i], '
        'input[aria-label*="pesquisar" i], input[aria-label*="search" i]'
    )

    async def tentar_preencher_campo():
        try:
            input_elements = await page.query_selector_all(input_seletor)
            logger.info(f"Campos de input candidatos: {len(input_elements)}")
            for idx, input_el in enumerate(input_elements):
                try:
                    box = await input_el.bounding_box()
                except Exception:
                    box = None
                if box and box.get('height', 0) > 10 and box.get('width', 0) > 100:
                    try:
                        await input_el.scroll_into_view_if_needed()
                        await input_el.click(timeout=500)
                    except Exception:
                        pass
                    await page.wait_for_timeout(150)
                    try:
                        await input_el.fill(keyword, timeout=800)
                        await page.keyboard.press("Enter")
                        logger.info(f"Pesquisa submetida via input índice {idx}")
                        return True
                    except Exception as e:
                        logger.debug(f"Falha a preencher input índice {idx}: {e}")
                        continue
        except Exception as e:
            logger.warning(f"Erro ao procurar campo: {e}")
            return False
        return False

    if await tentar_preencher_campo():
        return True

    # Ícones/botões
    botoes = await page.query_selector_all('button, a')
    logger.info(f"Botões/links para tentar abrir pesquisa: {len(botoes)}")
    for botao in botoes:
        try:
            html = (await botao.inner_html()).lower()
            texto = (await botao.inner_text()).lower()
        except Exception:
            continue
        if any(term in (html + texto) for term in ["search", "pesquisar", "procura", "lupa", "🔍"]):
            try:
                await botao.scroll_into_view_if_needed()
                await botao.click(timeout=600)
            except Exception:
                continue
            await page.wait_for_timeout(700)
            break

    if await tentar_preencher_campo():
        return True

    # Fallback JS
    try:
        ok = await page.evaluate(f'''
            () => {{
                const kw = {keyword!r};
                for (const input of document.querySelectorAll('input')) {{
                    const attrs = (input.placeholder + " " + input.name + " " + input.id + " " + input.className).toLowerCase();
                    if (attrs.includes("search") || attrs.includes("pesquisar") || attrs.includes("procura")) {{
                        input.focus();
                        input.value = kw;
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', bubbles: true }}));
                        input.form?.submit?.();
                        return true;
                    }}
                }}
                return false;
            }}
        ''')
        await page.wait_for_timeout(600)
        logger.info(f"Pesquisa via JS fallback: {ok}")
        return bool(ok)
    except Exception as e:
        logger.warning(f"Fallback JS falhou: {e}")
        return False


async def heuristica_seletor(page) -> Optional[str]:
    seletores = [
        'article',
        'div[class*="content"]',
        'div[class*="article"]',
        'div[id*="content"]',
        'section[class*="content"]',
        'main'
    ]
    for sel in seletores:
        try:
            elementos = await page.query_selector_all(sel)
            if elementos and len(elementos) > 0:
                logger.info(f"Seletor heurístico escolhido: {sel}")
                return sel
        except Exception:
            continue
    logger.info("Nenhum seletor heurístico encontrado; usar 'body'")
    return None


async def extrair_titulo(page) -> Optional[str]:
    seletores_titulo = [
        "h1",
        "header h1",
        "article h1",
        "section h1",
        "div[class*='title'] h1",
        "div[class*='header'] h1",
        "meta[property='og:title']",
        "title"
    ]
    for seletor in seletores_titulo:
        try:
            el = await page.query_selector(seletor)
            if el:
                if seletor.startswith("meta"):
                    titulo = await el.get_attribute("content")
                else:
                    titulo = await el.inner_text()
                if titulo and len(titulo.strip()) > 5:
                    return titulo.strip()
        except Exception:
            continue
    return None


def ensure_playwright_browsers_installed():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    try:
        import subprocess
        subprocess.run(
            ["python", "-m", "playwright", "install", "--dry-run"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        try:
            subprocess.run(["python", "-m", "playwright", "install", "chromium", "--with-deps"], check=True)
        except Exception:
            pass


async def route_intercept(route, request):
    url = request.url
    rtype = request.resource_type
    try:
        if BLOCK_ADS and any(host in url for host in AD_HOST_HINTS):
            return await route.abort()
        if BLOCK_IMAGES and rtype in {"image"}:
            return await route.abort()
        if BLOCK_MEDIA and rtype in {"media"}:
            return await route.abort()
        if BLOCK_FONTS and rtype in {"font"}:
            return await route.abort()
        return await route.continue_()
    except Exception:
        try:
            await route.continue_()
        except Exception:
            pass


async def keyword_in_content(page, seletor: str, keyword: str) -> bool:
    js = """
    (sel, kw) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const text = el.innerText || "";
      return text.toLowerCase().includes(kw.toLowerCase());
    }
    """
    try:
        return bool(await page.evaluate(js, seletor, keyword))
    except Exception:
        return False


async def keyword_in_body(page, keyword: str) -> bool:
    js = """
    (kw) => {
      const text = (document.body && document.body.innerText) ? document.body.innerText : "";
      return text.toLowerCase().includes(kw.toLowerCase());
    }
    """
    try:
        return bool(await page.evaluate(js, keyword))
    except Exception:
        return False


async def bot_scraper(site_url, keyword, max_results):
    logger.info(f"[START] bot_scraper site={site_url} kw='{keyword}' max={max_results}")
    resultados = []
    visited_urls = set()
    base_host = urlparse(site_url).netloc

    ensure_playwright_browsers_installed()
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--no-default-browser-check",
                    "--no-first-run",
                    "--disable-features=Translate",
                    "--blink-settings=imagesEnabled=false"
                ]
            )
        except PlaywrightError as e:
            logger.error(f"Falha a lançar o Chromium: {e}")
            raise

        context_kwargs = dict(
            java_script_enabled=True,
            accept_downloads=False,
            ignore_https_errors=True,
            viewport={"width": 360, "height": 640} if USE_MOBILE else {"width": 1280, "height": 800},
            device_scale_factor=1,
            user_agent=(
                "Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.0.0 Mobile Safari/537.36"
            ) if USE_MOBILE else (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.0.0 Safari/537.36"
            )
        )
        context = await browser.new_context(**context_kwargs)
        context.set_default_navigation_timeout(NAV_TIMEOUT)
        context.set_default_timeout(ACT_TIMEOUT)

        page = await context.new_page()
        await page.route("**/*", route_intercept)

        try:
            await page.goto(site_url, wait_until='domcontentloaded')
            logger.info(f"Navegou para site base: {site_url}")
        except Exception as e:
            logger.exception(f"Erro ao abrir site base: {e}")
            await context.close()
            await browser.close()
            return site_url, []

        await aceitar_cookies(page)
        await asyncio.sleep(0.3)

        sucesso = await encontrar_e_preencher_pesquisa(page, keyword)
        if not sucesso:
            logger.warning("Não conseguiu submeter a pesquisa. Abort.")
            await context.close()
            await browser.close()
            return site_url, []

        try:
            await page.wait_for_load_state('networkidle', timeout=9000)
        except Exception:
            logger.info("Timeout em networkidle (seguimos em frente).")

        await clicar_carregar_mais(page, max_clicks=2)

        anchors = await page.query_selector_all('a')
        total_anchors = len(anchors)
        logger.info(f"Âncoras encontradas na página de resultados: {total_anchors}")

        reason_counts = {
            "blocked_by_url_hint": 0,
            "blocked_by_text_hint": 0,
            "text_too_short": 0,
            "other_domain": 0,
            "news_hint": 0,
            "generic_ok": 0
        }

        candidates = []
        for a in anchors:
            if len(candidates) >= MAX_CANDIDATES:
                break
            try:
                href = await a.get_attribute("href")
                full_url = normalize_url(page.url, href)
                if not full_url:
                    continue
                text = (await a.inner_text()) or ""
                # Usa bounding_box só para afastar header fixo
                try:
                    box = await a.bounding_box()
                    if box and box.get("y", 1000) <= 120:
                        continue
                except Exception:
                    pass

                ok, reason = link_filter_reason(base_host, full_url, text)
                if ok:
                    if full_url not in visited_urls:
                        candidates.append((full_url, text.strip()))
                        visited_urls.add(full_url)
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            except Exception:
                continue

        logger.info(f"Candidatos recolhidos: {len(candidates)} (limite {MAX_CANDIDATES})")
        if SHOW_LINK_REASONS:
            logger.info(f"Motivos de filtragem: {reason_counts}")

        # ordenar por tamanho do texto (mais contexto) e limitar
        candidates.sort(key=lambda x: -len(x[1]))
        top_links = candidates[:MAX_TOP_LINKS]
        logger.info(f"Top links a visitar: {len(top_links)}")

        visited_count = 0
        matches_count = 0

        for url, cand_text in top_links:
            if len(resultados) >= max_results:
                break
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT)
                await aceitar_cookies(page)
                await asyncio.sleep(0.2)
                current_url = page.url
                site_name = get_site_name(current_url)

                seletor_corpo = await heuristica_seletor(page)
                corpo_sel = seletor_corpo or "article"
                # se não existir article, caímos para body
                if seletor_corpo is None:
                    corpo_sel = "body"

                has_kw_sel = await keyword_in_content(page, corpo_sel, keyword)
                has_kw_body = False if has_kw_sel else await keyword_in_body(page, keyword)
                has_kw = has_kw_sel or has_kw_body

                titulo = await extrair_titulo(page)

                logger.info(
                    f"[VISIT] {current_url} | sel={corpo_sel} | match_sel={has_kw_sel} | "
                    f"match_body={has_kw_body} | title={'OK' if titulo else 'N/A'}"
                )

                if has_kw or ALLOW_NO_MATCH:
                    resultados.append((titulo or "", current_url, site_name))
                    matches_count += 1 if has_kw else 0

                visited_count += 1

                # voltar à lista
                try:
                    await page.go_back(timeout=8000)
                except Exception:
                    # Se falhar voltar, tentamos abrir de novo a página de resultados
                    try:
                        await page.goto(site_url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT)
                    except Exception:
                        pass
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.warning(f"Falha a abrir link: {url} | {e}")

        logger.info(f"[DONE] visitados={visited_count} | resultados={len(resultados)} | matches_exatos={matches_count}")

        await context.close()
        await browser.close()
        gc.collect()

    return site_url, resultados


async def executar_scraper(site_url, keyword, max_results):
    try:
        _, resultados = await bot_scraper(site_url, keyword, max_results)
        return resultados
    except Exception as e:
        logger.exception(f"executar_scraper falhou: {e}")
        return []


async def rodar_varias_keywords(site_url, keywords, max_results=3):
    resultados_por_keyword = []
    for kw in keywords:
        res = await executar_scraper(site_url, kw, max_results)
        resultados_por_keyword.append((kw, res))
        await asyncio.sleep(0.05)  # pequeno respiro para GC
    return resultados_por_keyword