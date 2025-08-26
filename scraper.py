import asyncio
from playwright.async_api import async_playwright
import logging
from urllib.parse import urlparse, urljoin, urldefrag
import os
import subprocess
from dotenv import load_dotenv
from playwright._impl._errors import Error as PlaywrightError

load_dotenv()

chrome_version = os.getenv("CHROME_VERSION", "137")
max_wait = int(os.getenv("MAX_WAIT_TIME", "10"))

# Configuração básica do logging
logging.basicConfig(
    filename="scraper_log.txt",
    filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

LOGIN_EMAIL = os.getenv("LOGIN_EMAIL", "")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")

# Heurísticas de filtragem de links
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
    # Simplificação: usa os 2 últimos segmentos (bom para .pt/.com)
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def normalize_url(base_url: str, href: str) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    full = urljoin(base_url, href)
    full, _ = urldefrag(full)  # remove #fragment
    if not full.startswith(("http://", "https://")):
        return None
    return full


def host_allowed(candidate_host: str, base_host: str) -> bool:
    # Permite mesmo host ou subdomínios do mesmo domínio de base, excluindo subdomínios "ajuda", etc.
    base_root = get_base_domain(base_host)
    if candidate_host == base_host or candidate_host.endswith("." + base_root):
        # Excluir subdomínios indesejados
        sub_parts = candidate_host.replace("." + base_root, "")
        sub = sub_parts.split(".")[-1] if sub_parts else ""
        if sub and sub.lower() in EXCLUDED_SUBDOMAINS:
            return False
        return True
    return False


def is_relevant_link(base_host: str, url: str, text: str) -> bool:
    u = url.lower()
    t = (text or "").lower().strip()

    # Exclusões óbvias
    if any(b in u for b in BLOCKED_URL_HINTS):
        return False
    if any(b in t for b in BLOCKED_URL_HINTS):
        return False

    # Evita urls muito curtas, sem conteúdo, âncoras de navegação
    if len(t) < 15:
        return False

    # Domínio deve ser o mesmo (ou subdomínio permitido)
    cand_host = urlparse(url).netloc
    if not host_allowed(cand_host, base_host):
        return False

    # Preferir caminhos de notícia
    if any(h in u for h in NEWS_PATH_HINTS) or any(h in t for h in NEWS_PATH_HINTS):
        return True

    # Caso não tenha hints, ainda pode ser relevante, mas menos provável
    return True


async def clicar_botao_todos(page):
    try:
        elementos = await page.query_selector_all('button, a')
        for el in elementos:
            try:
                texto = (await el.inner_text()).lower()
            except Exception:
                continue
            if "todos" in texto:
                print(f"[INFO] Clicando no botão com 'todos': '{texto.strip()}'")
                try:
                    await el.scroll_into_view_if_needed()
                except Exception:
                    pass
                await el.click()
                await page.wait_for_timeout(3000)
                return True
    except:
        pass
    print("[INFO] Nenhum botão com 'todos' encontrado.")
    return False


async def clicar_carregar_mais(page, max_clicks: int = 3):
    # Tenta expandir listas com "Mais notícias / Ver mais / Mostrar mais / Carregar mais"
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
                    await btn.click()
                    await page.wait_for_timeout(1500)
                    print(f"[INFO] Clique em '{tx}' para carregar mais.")
                    clicks += 1
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break
    if clicks == 0:
        print("[INFO] Nenhum botão de 'carregar mais' encontrado.")


async def aceitar_cookies(page):
    print("[INFO] Verificando popup de cookies...")
    await page.wait_for_timeout(1200)
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
        'div[class*="consent"] button:has-text("Aceitar")',
        'div[class*="cookie"] button:has-text("OK")',
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
                    await btn.click(timeout=1000)
                except Exception:
                    try:
                        await page.evaluate("(el) => el.click()", btn)
                    except Exception:
                        continue
                print(f"[INFO] Cookies aceites via seletor: {selector}")
                await page.wait_for_timeout(500)
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
                        await btn.click()
                        print(f"[INFO] Cookies aceites dentro de iframe via: {selector}")
                        await page.wait_for_timeout(500)
                        return
                except Exception:
                    continue
    except Exception:
        pass
    print("[INFO] Nenhum popup de cookies encontrado/necessário.")


async def ollama_classify_links(links_texts, keyword):
    import re
    keyword_lower = keyword.lower()
    resultados_relevantes = []
    for url, text in links_texts:
        text_lower = (text or "").lower().strip()
        if any(palavra in text_lower for palavra in [
            "login", "entrar", "inscrever", "contato", "sobre", "privacidade", "termos", "cookies"
        ]):
            continue
        if any(palavra in (url or "").lower() for palavra in [
            "login", "auth", "contact", "about", "signup", "privacy", "terms"
        ]):
            continue
        if len(text_lower) < 20 or re.match(r"^\W+$", text_lower):
            continue
        if keyword_lower in text_lower or any(word in text_lower for word in keyword_lower.split()):
            score = 2
        else:
            score = 1
        resultados_relevantes.append((score, url, text))
    resultados_relevantes.sort(key=lambda x: (-x[0], -len(x[2])))
    return [(url, text) for _, url, text in resultados_relevantes[:10]]


async def tentar_login(page):
    if "login" in page.url or "signin" in page.url or "autentica" in page.url:
        try:
            print("[INFO] Tentando login automático...")
            await page.fill('input[type="email"], input[name*="email"]', LOGIN_EMAIL)
            await asyncio.sleep(1)
            await page.fill('input[type="password"], input[name*="pass"]', LOGIN_PASSWORD)
            await asyncio.sleep(1)
            await page.click('button[type="submit"], input[type="submit"],'
                             'button[type="continuar"], input[type="continuar"],'
                             'button[type="Continuar"], input[type="Continuar"],'
                             'button[type="entrar"], input[type="entrar"],'
                             'button[type="Entrar"], input[type="Entrar"]')
            await page.wait_for_timeout(3000)
            print("[INFO] Login tentado.")
        except Exception as e:
            print(f"[ERRO] Falha no login: {e}")


async def encontrar_e_preencher_pesquisa(page, keyword):
    print("[INFO] A procurar campo de pesquisa...")
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
                        await input_el.click()
                    except Exception:
                        pass
                    await page.wait_for_timeout(250)
                    try:
                        await input_el.fill(keyword)
                        await page.keyboard.press("Enter")
                        print("[INFO] Campo de pesquisa preenchido.")
                        return True
                    except Exception:
                        continue
        except Exception as e:
            print(f"[ERRO] ao tentar preencher campo: {e}")
        return False

    if await tentar_preencher_campo():
        return True

    print("[INFO] Tentar clicar na lupa...")
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
                await botao.click()
            except Exception:
                continue
            await page.wait_for_timeout(1200)
            break

    if await tentar_preencher_campo():
        return True

    await page.wait_for_timeout(1000)
    print("[INFO] Última tentativa via JavaScript...")
    try:
        await page.evaluate(f'''
            () => {{
                const kw = {keyword!r};
                const inputs = document.querySelectorAll('input');
                for (let input of inputs) {{
                    let attrs = (input.placeholder + " " + input.name + " " + input.id + " " + input.className).toLowerCase();
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
        await page.wait_for_timeout(1200)
        print("[INFO] Pesquisa via JavaScript enviada.")
        return True
    except Exception as e:
        print(f"[ERRO] JS Search: {e}")
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
                print(f"[INFO] Seletor heurístico encontrado: {sel}")
                return sel
        except:
            continue
    return None


async def identificar_seletor_corpo(page_content: str):
    # Mantido conforme o teu stub
    await asyncio.sleep(2)
    resposta = "article"
    print(f"[INFO] AI sugeriu o seletor: {resposta}")
    return resposta


async def extrair_texto_conteudo(page, seletor):
    try:
        elemento = await page.query_selector(seletor)
        if elemento:
            texto = await elemento.inner_text()
            print(f"[INFO] Tamanho do texto extraído: {len(texto)}")
            return texto
    except Exception as e:
        print(f"[ERRO] ao extrair texto do seletor {seletor}: {e}")
    return ""


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


async def aceitar_consentimentos(page):
    await page.wait_for_timeout(2500)
    consent_texts = [
        "Aceitar", "Consentir", "Concordo", "Sim", "OK", "Aceito", "Permitir", "Aceitar tudo"
    ]
    for text in consent_texts:
        try:
            button = await page.query_selector(f'button:has-text("{text}")')
            if button:
                await button.scroll_into_view_if_needed()
                await button.click()
                print(f"[INFO] Consentimento aceito: {text}")
                await page.wait_for_timeout(800)
                return
        except:
            pass
    for frame in page.frames:
        for text in consent_texts:
            try:
                button = await frame.query_selector(f'button:has-text("{text}")')
                if button:
                    await button.scroll_into_view_if_needed()
                    await button.click()
                    print(f"[INFO] Consentimento aceito em iframe: {text}")
                    await page.wait_for_timeout(800)
                    return
            except:
                pass
    print("[INFO] Nenhum botão de consentimento encontrado.")


async def extrair_titulo(page):
    seletores_titulo = [
        "h1",
        "header h1",
        "article h1",
        "section h1",
        "div[class*='title'] h1",
        "div[class*='header'] h1",
        "h2",
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


async def bot_scraper(site_url, keyword, max_results):
    resultados = []
    visited_urls = set()
    base_host = urlparse(site_url).netloc

    ensure_playwright_browsers_installed()
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
        except PlaywrightError as e:
            if "Executable doesn't exist" in str(e):
                ensure_playwright_browsers_installed()
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
            else:
                raise

        context = await browser.new_context()
        page = await context.new_page()

        print(f"[INFO] Acessando o site: {site_url}")
        await page.goto(site_url, wait_until='domcontentloaded')
        await aceitar_cookies(page)
        await asyncio.sleep(1.2)

        sucesso = await encontrar_e_preencher_pesquisa(page, keyword)
        if not sucesso:
            await browser.close()
            return site_url, []

        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            print("[WARN] Timeout ao esperar pelos resultados.")

        # Tenta carregar mais resultados, se existir
        await clicar_botao_todos(page)
        await clicar_carregar_mais(page, max_clicks=3)

        # Recolher links candidatos
        anchors = await page.query_selector_all('a')
        candidates = []
        for a in anchors:
            try:
                href = await a.get_attribute("href")
                full_url = normalize_url(page.url, href)
                if not full_url:
                    continue
                text = (await a.inner_text()) or ""
                box = await a.bounding_box()
                # Evita header (y < 150) e elementos invisíveis
                if box and box.get("y", 1000) > 150 and is_relevant_link(base_host, full_url, text):
                    if full_url not in visited_urls:
                        candidates.append((full_url, text.strip()))
                        visited_urls.add(full_url)
            except Exception:
                continue

        # Se houver muitos, usa a tua função de classificação para priorizar
        if len(candidates) > 12:
            top_links = await ollama_classify_links(candidates, keyword)
        else:
            # ordena por comprimento do texto (mais contexto)
            candidates.sort(key=lambda x: -len(x[1]))
            top_links = candidates[:12]

        for url, _text in top_links:
            if len(resultados) >= max_results:
                break
            try:
                print(f"[INFO] Abrindo notícia: {url}")
                await page.goto(url, wait_until='domcontentloaded')
                await aceitar_cookies(page)
                await asyncio.sleep(0.8)

                current_url = page.url
                site_name = get_site_name(current_url)

                seletor_corpo = await heuristica_seletor(page)
                corpo_sel = seletor_corpo or "article"
                texto = await extrair_texto_conteudo(page, corpo_sel)

                if texto and (keyword.lower() in texto.lower()):
                    titulo = await extrair_titulo(page)
                    resultados.append((titulo or "", current_url, site_name))
                    print(f"[MATCH] Palavra-chave encontrada. Título: {titulo}")
                else:
                    print("[INFO] Palavra-chave não encontrada no conteúdo.")

                await page.go_back()
                await asyncio.sleep(0.6)
            except Exception as e:
                print(f"[ERRO] {url}: {e}")
                continue

        await browser.close()

    return site_url, resultados


async def rodar_varias_keywords(site_url, keywords, max_results=3):
    tarefas = [executar_scraper(site_url, keyword, max_results) for keyword in keywords]
    resultados_por_keyword = await asyncio.gather(*tarefas)
    return list(zip(keywords, resultados_por_keyword))


async def executar_scraper(site_url, keyword, max_results):
    _, resultados = await bot_scraper(site_url, keyword, max_results)
    return resultados