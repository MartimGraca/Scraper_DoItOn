import asyncio
import gc
import logging
import os
import subprocess
from urllib.parse import urlparse, urljoin, urldefrag

from dotenv import load_dotenv
from playwright._impl._errors import Error as PlaywrightError
from playwright.async_api import async_playwright

load_dotenv()

# Limites e opções de performance/memória
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "40"))       # limite de links recolhidos na página de resultados
MAX_TOP_LINKS = int(os.getenv("MAX_TOP_LINKS", "6"))          # máximo de artigos a abrir por keyword
NAV_TIMEOUT = int(os.getenv("NAV_TIMEOUT_MS", "15000"))       # timeout de navegação
ACT_TIMEOUT = int(os.getenv("ACTION_TIMEOUT_MS", "8000"))     # timeout de ações (click/fill/etc)
BLOCK_IMAGES = os.getenv("BLOCK_IMAGES", "1") == "1"
BLOCK_MEDIA = os.getenv("BLOCK_MEDIA", "1") == "1"
BLOCK_FONTS = os.getenv("BLOCK_FONTS", "1") == "1"
BLOCK_ADS = os.getenv("BLOCK_ADS", "1") == "1"                # bloquear domínios comuns de ads/trackers
USE_MOBILE = os.getenv("USE_MOBILE", "1") == "1"              # usar viewport/UA mobile para páginas mais leves

# Logging básico
logging.basicConfig(
    filename="scraper_log.txt",
    filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

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

def normalize_url(base_url: str, href: str) -> str | None:
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

def is_relevant_link(base_host: str, url: str, text: str) -> bool:
    u = url.lower()
    t = (text or "").lower().strip()

    if any(b in u for b in BLOCKED_URL_HINTS):
        return False
    if any(b in t for b in BLOCKED_URL_HINTS):
        return False

    if len(t) < 15:
        return False

    cand_host = urlparse(url).netloc
    if not host_allowed(cand_host, base_host):
        return False

    if any(h in u for h in NEWS_PATH_HINTS) or any(h in t for h in NEWS_PATH_HINTS):
        return True

    return True

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
                    break
            except Exception:
                continue
        if not clicked:
            break

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
                return
        except Exception:
            continue
    # iframes (rápido)
    try:
        for frame in page.frames:
            for selector in cookie_selectors:
                try:
                    btn = await frame.query_selector(selector)
                    if btn:
                        await btn.click(timeout=800)
                        return
                except Exception:
                    continue
    except Exception:
        pass

async def encontrar_e_preencher_pesquisa(page, keyword):
    input_seletor = (
        'input[type="search"], input[type="text"], '
        'input[placeholder*="pesquisar" i], input[placeholder*="search" i], '
        'input[name*="search" i], input[id*="search" i], input[class*="search" i], '
        'input[aria-label*="pesquisar" i], input[aria-label*="search" i]'
    )

    async def tentar_preencher_campo():
        try:
            input_elements = await page.query_selector_all(input_seletor)
            for input_el in input_elements:
                box = await input_el.bounding_box()
                if box and box['height'] > 10 and box['width'] > 100:
                    try:
                        await input_el.scroll_into_view_if_needed()
                        await input_el.click(timeout=500)
                    except Exception:
                        pass
                    await page.wait_for_timeout(150)
                    try:
                        await input_el.fill(keyword, timeout=800)
                        await page.keyboard.press("Enter")
                        return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    if await tentar_preencher_campo():
        return True

    # Tentar abrir pesquisa por ícone
    botoes = await page.query_selector_all('button, a')
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

    # fallback JS curto
    try:
        await page.evaluate(f'''
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
        return True
    except Exception:
        return False

async def heuristica_seletor(page):
    seletores = [
        'article',
        'div[class*="content"]',
        'div[class*="article"]',
        'div[id*="content"]',
        'section[class*="content"]'
    ]
    for sel in seletores:
        try:
            elementos = await page.query_selector_all(sel)
            if elementos and len(elementos) > 0:
                return sel
        except:
            continue
    return None

async def extrair_titulo(page):
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
        except:
            continue
    return None

def ensure_playwright_browsers_installed():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
    try:
        subprocess.run(
            ["python", "-m", "playwright", "install", "--dry-run"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        try:
            subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
        except Exception:
            try:
                subprocess.run(["python", "-m", "playwright", "install", "chromium", "--with-deps"], check=True)
            except Exception:
                pass

# NOVO: bloqueio de recursos pesados e domínios de ads/trackers
AD_HOST_HINTS = [
    "doubleclick.net", "googlesyndication.com", "googletagmanager.com", "google-analytics.com",
    "facebook.net", "twitter.com/i", "scorecardresearch.com", "criteo.com", "taboola.com",
    "outbrain.com", "cloudfront.net", "adservice.google.com", "hotjar.com"
]

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
        # stylesheets geralmente são necessários para layout/cookies; mantemos
        return await route.continue_()
    except Exception:
        try:
            await route.continue_()
        except Exception:
            pass

# NOVO: verificar keyword no DOM sem puxar texto para Python
async def keyword_in_content(page, seletor, keyword: str) -> bool:
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

async def bot_scraper(site_url, keyword, max_results):
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
                    "--disable-dev-shm-usage",            # importante em ambientes com pouca memória/SHM
                    "--disable-extensions",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--no-default-browser-check",
                    "--no-first-run",
                    "--disable-features=Translate",
                    "--blink-settings=imagesEnabled=false" # reforço para imagens
                ]
            )
        except PlaywrightError as e:
            if "Executable doesn't exist" in str(e):
                ensure_playwright_browsers_installed()
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
            else:
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
        await page.route("**/*", route_intercept)  # NOVO: bloquear recursos pesados

        try:
            await page.goto(site_url, wait_until='domcontentloaded')
        except Exception:
            await browser.close()
            return site_url, []

        await aceitar_cookies(page)
        await asyncio.sleep(0.5)

        sucesso = await encontrar_e_preencher_pesquisa(page, keyword)
        if not sucesso:
            await browser.close()
            return site_url, []

        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except:
            pass

        await clicar_carregar_mais(page, max_clicks=2)

        anchors = await page.query_selector_all('a')
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
                box = await a.bounding_box()
                if box and box.get("y", 1000) > 150 and is_relevant_link(base_host, full_url, text):
                    if full_url not in visited_urls:
                        candidates.append((full_url, text.strip()))
                        visited_urls.add(full_url)
            except Exception:
                continue

        # ordenar por tamanho do texto (mais contexto) e limitar
        candidates.sort(key=lambda x: -len(x[1]))
        top_links = candidates[:MAX_TOP_LINKS]

        for url, _text in top_links:
            if len(resultados) >= max_results:
                break
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT)
                await aceitar_cookies(page)
                await asyncio.sleep(0.3)

                current_url = page.url
                site_name = get_site_name(current_url)

                seletor_corpo = await heuristica_seletor(page)
                corpo_sel = seletor_corpo or "article"

                # Checagem barata no browser, sem puxar texto para Python
                has_kw = await keyword_in_content(page, corpo_sel, keyword)

                if has_kw:
                    titulo = await extrair_titulo(page)
                    resultados.append((titulo or "", current_url, site_name))
                # Retorna à lista de resultados com o mesmo tab (sem abrir novas páginas)
                await page.go_back(timeout=8000)
                await asyncio.sleep(0.2)
            except Exception:
                continue

        # fechar e limpar
        await context.close()
        await browser.close()
        gc.collect()

    return site_url, resultados

# Processar keywords em série (memória estável). Se quiser concorrência, use um Semaphore baixo (ex.: 2)
async def executar_scraper(site_url, keyword, max_results):
    _, resultados = await bot_scraper(site_url, keyword, max_results)
    return resultados

async def rodar_varias_keywords(site_url, keywords, max_results=3):
    resultados_por_keyword = []
    for kw in keywords:
        res = await executar_scraper(site_url, kw, max_results)
        resultados_por_keyword.append((kw, res))
        # pequena pausa para deixar o GC trabalhar
        await asyncio.sleep(0.1)
    return resultados_por_keyword