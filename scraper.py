import asyncio
from playwright.async_api import async_playwright
import logging
from urllib.parse import urlparse
from urllib.parse import urlparse, urljoin
import os
from dotenv import load_dotenv

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


from urllib.parse import urlparse


def get_site_name(url):

    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    parts = domain.split('.')


    subdominios_ignorados = ['www', 'news']
    filtered_parts = [part for part in parts if part not in subdominios_ignorados]

    # Pegar o penúltimo segmento (domínio principal) se houver mais de dois segmentos
    if len(filtered_parts) > 1:
        site_name = filtered_parts[-2].capitalize()
    else:
        site_name = filtered_parts[0].capitalize()

    return site_name





async def clicar_botao_todos(page):
    try:
        elementos = await page.query_selector_all('button, a')
        for el in elementos:
            texto = (await el.inner_text()).lower()
            if "todos" in texto:
                print(f"[INFO] Clicando no botão com 'todos': '{texto.strip()}'")
                await el.click()
                await page.wait_for_timeout(3000)
                return True
    except:
        pass
    print("[INFO] Nenhum botão com 'todos' encontrado.")
    return False


async def aceitar_cookies(page):
    print("[INFO] Verificando popup de cookies...")
    await page.wait_for_timeout(2000)


    cookie_selectors = [
        'button[aria-label*="aceitar" i]',
        'button:has-text("Aceitar")',
        'button:has-text("Accept")',
        'button:has-text("Concordo")',
        'button[aria-label*="concordo" i]',
        'button[aria-label*="Consentir" i]',
        'button:has-text("Consentir")',
        'button[aria-label*="consentir" i]',
        'button:has-text("consentir")',
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
                    await btn.click(force=True, timeout=1000)
                    print(f"[INFO] Cookies aceites via seletor: {selector}")
                    await page.wait_for_timeout(800)
                    return
                except Exception as e:
                    # Alternativa via JavaScript caso .click() normal falhe
                    try:
                        await page.evaluate("(el) => el.click()", btn)
                        print(f"[INFO] Cookies aceites via JS: {selector}")
                        await page.wait_for_timeout(800)
                        return
                    except:
                        continue
        except:
            continue

    # Verifica se há algum iframe de consentimento
    await page.wait_for_timeout(2000)
    frames = page.frames
    for frame in frames:
        try:
            for selector in cookie_selectors:
                btn = await frame.query_selector(selector)
                if btn:
                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    print(f"[INFO] Cookies aceites dentro de iframe via: {selector}")
                    await page.wait_for_timeout(800)
                    return
        except:
            continue

    print("[INFO] Nenhum popup de cookies encontrado ou necessário.")



async def ollama_classify_links(links_texts, keyword):
    """
    Classifica links com base no texto âncora e URL.
    Filtra links irrelevantes (login, contato, sobre, etc) e prioriza notícias relacionadas à keyword.
    """
    import re

    keyword_lower = keyword.lower()
    resultados_relevantes = []

    for url, text in links_texts:
        text_lower = text.lower().strip()

        # Ignorar links com palavras irrelevantes
        if any(palavra in text_lower for palavra in [
            "login", "entrar", "inscrever", "contato", "sobre", "privacidade", "termos", "cookies"
        ]):
            continue
        if any(palavra in url.lower() for palavra in [
            "login", "auth", "contact", "about", "signup", "privacy", "terms"
        ]):
            continue

        # Ignorar textos muito curtos ou genéricos
        if len(text_lower) < 20 or re.match(r"^\W+$", text_lower):
            continue

        # Verificar se o texto tem a keyword ou é potencialmente relacionado
        if keyword_lower in text_lower or any(word in text_lower for word in keyword_lower.split()):
            score = 2
        else:
            score = 1  # Potencialmente relacionado mesmo sem keyword

        resultados_relevantes.append((score, url, text))

    # Ordenar por score e comprimento do texto (mais completo)
    resultados_relevantes.sort(key=lambda x: (-x[0], -len(x[2])))

    # Retornar até 10 links mais promissores
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
                    await input_el.scroll_into_view_if_needed()
                    await input_el.click()
                    await page.wait_for_timeout(300)
                    await input_el.fill(keyword)
                    await page.keyboard.press("Enter")
                    print("[INFO] Campo de pesquisa preenchido.")
                    return True
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
            if any(term in (html + texto) for term in ["search", "pesquisar", "procura", "lupa", "🔍"]):
                await botao.scroll_into_view_if_needed()
                await botao.click()
                await page.wait_for_timeout(1500)
                break
        except:
            continue

    if await tentar_preencher_campo():
        return True
    await page.wait_for_timeout(2000)
    print("[INFO] Última tentativa via JavaScript...")
    try:
        await page.evaluate(f'''
            () => {{
                const inputs = document.querySelectorAll('input');
                for (let input of inputs) {{
                    let attrs = (input.placeholder + " " + input.name + " " + input.id + " " + input.className).toLowerCase();
                    if (attrs.includes("search") || attrs.includes("pesquisar") || attrs.includes("procura")) {{
                        input.focus();
                        input.value = "{keyword}";
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', bubbles: true }}));
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.form?.submit?.();
                        return true;
                    }}
                }}
                return false;
            }}
        ''')
        await page.wait_for_timeout(2000)
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
    # Simulação da chamada para API Ollama
    content_limit = 30000
    trimmed_content = page_content[:content_limit]
    prompt = f"""
Você é um assistente especializado em extrair conteúdo principal de notícias de páginas web.  
Abaixo está um fragmento do HTML da página, contendo a estrutura da notícia.  
Seu objetivo é encontrar o seletor CSS que aponta para o container principal da notícia (onde está o texto maior ou entao o texto mais acima).  

Aqui está o HTML (cortado para 30 mil caracteres):

\"\"\"{trimmed_content}\"\"\"

Retorne apenas um seletor CSS que melhor seleciona o corpo principal e do título da página e identifica as noticías.  
Prefira seletores que envolvam <article>, <div> ou <section> com bastante texto e poucos links ou menus.  
Se não conseguir identificar, retorne "body".
"""
    print("[INFO] Chamando AI para identificar seletor principal da notícia...")
    await asyncio.sleep(2)  # Simulando delay da API
    # Exemplo fixo de resposta, substitui com tua chamada real:
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


async def bot_scraper(site_url, keyword, max_results):
    resultados = []
    visited_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"[INFO] Acessando o site: {site_url}")
        await page.goto(site_url, wait_until='domcontentloaded')
        await aceitar_cookies(page)
        await asyncio.sleep(3)

        sucesso = await encontrar_e_preencher_pesquisa(page, keyword)
        if not sucesso:
            return site_url, []

        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            print("[WARN] Timeout ao esperar pelos resultados.")

        await clicar_botao_todos(page)

        links = await page.query_selector_all('a')
        noticia_links = []
        for link in links:
            try:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                box = await link.bounding_box()
                if (
                        href and text and len(text.strip()) > 20 and
                        box and box['y'] > 150
                ):
                    full_url = urljoin(site_url, href)
                    if full_url not in visited_urls:
                        noticia_links.append(full_url)
                        visited_urls.add(full_url)
            except:
                continue

        for url in noticia_links:
            if len(resultados) >= max_results:
                break
            try:
                print(f"[INFO] Abrindo notícia: {url}")
                await page.goto(url, wait_until='domcontentloaded')
                await aceitar_cookies(page)
                await asyncio.sleep(3)

                # Identificar o nome do site a partir da URL atual
                current_url = page.url  # URL da página atual
                site_name = get_site_name(current_url)
                print(f"[INFO] Nome do site identificado: {site_name}")

                # Extrair o conteúdo da notícia
                seletor_corpo = await heuristica_seletor(page)
                texto = await extrair_texto_conteudo(page, seletor_corpo)

                # Verificar se a palavra-chave está presente
                if keyword.lower() in texto.lower():
                    titulo = await extrair_titulo(page)
                    resultados.append((current_url, site_name, titulo))
                    print(f"[MATCH] Palavra-chave encontrada. Título: {titulo}")
                else:
                    print(f"[INFO] Palavra-chave não encontrada no conteúdo da notícia.")

                await page.go_back()
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[ERRO] {url}: {e}")
                continue
        await browser.close()

    return site_url, resultados




async def aceitar_consentimentos(page):
    await page.wait_for_timeout(2500)

    consent_texts = [
        "Aceitar", "Consentir", "Concordo", "Sim", "OK", "Aceito", "Permitir", "Aceitar tudo"
    ]

    # Verificar fora de iframes
    for text in consent_texts:
        try:
            button = await page.query_selector(f'button:has-text("{text}")')
            if button:
                await button.scroll_into_view_if_needed()
                await button.click()
                print(f"[INFO] Consentimento aceito: {text}")
                await page.wait_for_timeout(1000)
                return
        except:
            pass

    # Verificar dentro de iframes
    for frame in page.frames:
        for text in consent_texts:
            try:
                button = await frame.query_selector(f'button:has-text("{text}")')
                if button:
                    await button.scroll_into_view_if_needed()
                    await button.click()
                    print(f"[INFO] Consentimento aceito em iframe: {text}")
                    await page.wait_for_timeout(1000)
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
            "h2",  # fallback
            "meta[property='og:title']",
            "title"
        ]

        for seletor in seletores_titulo:
            try:
                el = await page.query_selector(seletor)
                if el:
                    # Meta tag special case
                    if seletor.startswith("meta"):
                        titulo = await el.get_attribute("content")
                    else:
                        titulo = await el.inner_text()
                    if titulo and len(titulo.strip()) > 5:
                        return titulo.strip()
            except:
                continue

        return None


async def rodar_varias_keywords(site_url, keywords, max_results=3):
    tarefas = [
        executar_scraper(site_url, keyword, max_results)
        for keyword in keywords
    ]
    resultados_por_keyword = await asyncio.gather(*tarefas)

    # Combina resultados com suas palavras-chave associadas
    return list(zip(keywords, resultados_por_keyword))


async def executar_scraper(site_url, keyword, max_results):
    _, resultados = await bot_scraper(site_url, keyword, max_results)
    return resultados

