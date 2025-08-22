import os
import re
import time
import gc
from datetime import datetime
from urllib.parse import urlparse, urlunparse, urljoin, parse_qs, urlencode, quote_plus

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, ElementClickInterceptedException,
    ElementNotInteractableException, NoSuchElementException, StaleElementReferenceException
)

# Configurações principais
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
PAGELOAD_TIMEOUT = 25
SCRIPT_TIMEOUT = 20
WAIT_SHORT = 0.2
WAIT_MED = 0.6

# Limites opcionais para controlar memória/tempo (0 = sem limite)
MAX_LINKS_PER_KEYWORD = int(os.getenv("MAX_LINKS_PER_KEYWORD", "0") or "0")
MAX_PAGES_PER_KEYWORD = int(os.getenv("MAX_PAGES_PER_KEYWORD", "0") or "0")


def ensure_dirs():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    ensure_dirs()
    line = f"[{now_str()}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# Sem screenshots (acelera e reduz memória)
def save_shot(driver, name):
    return

# HTML dump apenas quando necessário (ex.: 0 links)
def save_html(driver, name):
    ensure_dirs()
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        html = driver.page_source
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"[DEBUG] HTML dump guardado: {path}")
    except Exception as e:
        log(f"[DEBUG] Falhou guardar HTML dump ({e})")

def open_url_with_timeout(driver, url, timeout=PAGELOAD_TIMEOUT, soft_wait=0.8):
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    except WebDriverException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    time.sleep(soft_wait)

def try_click(driver, el, prefix="click"):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(WAIT_SHORT)
    except Exception:
        pass

    try:
        ActionChains(driver).move_to_element(el).pause(0.05).click(el).perform()
        return True
    except Exception:
        pass

    try:
        el.click()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        pass

    try:
        driver.execute_script("""
            var overlays = document.querySelectorAll(
              'div[role=dialog], .modal, .overlay, .popup, [aria-hidden="true"], .fc-dialog-container, #onetrust-banner-sdk'
            );
            overlays.forEach(o=>{ try{ o.style.display='none'; o.remove(); }catch(e){} });
        """)
        time.sleep(WAIT_SHORT)
        driver.execute_script("arguments[0].click();", el)
        return True
    except Exception:
        pass

    return False

def normalize_google_href(href, base="https://www.google.com"):
    try:
        if href.startswith("/"):
            return urljoin(base, href)
        return href
    except Exception:
        return href

# -------------------------------------------------------------
# Cookies
# -------------------------------------------------------------
def localizar_botao_por_textos(driver, textos):
    xps = []
    for t in textos:
        tnorm = t.replace("'", "\\'")
        xp_cond = f"contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{tnorm.lower()}')"
        xps.extend([
            f"//button[{xp_cond}]",
            f"//div[{xp_cond}]",
            f"//span[{xp_cond}]",
            f"//a[{xp_cond}]",
        ])
    for xp in xps:
        try:
            els = driver.find_elements(By.XPATH, xp)
            for el in els:
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    return None

def aceitar_cookies_se_existem(driver, prefix="cookies"):
    try:
        log("[DEBUG] A tentar aceitar cookies...")
        time.sleep(0.5)
        textos = ['Aceitar tudo','Accept all','Aceitar','Concordo','Consent','Agree','OK','Aceitar cookies','Aceitar todos']
        btn = localizar_botao_por_textos(driver, textos)
        if btn and try_click(driver, btn, prefix=f"{prefix}_out"):
            log("[DEBUG] Cookies aceites (fora iframe).")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            return True

        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for i, fr in enumerate(iframes):
            try:
                driver.switch_to.frame(fr)
                time.sleep(0.2)
                btn = localizar_botao_por_textos(driver, textos)
                if btn and try_click(driver, btn, prefix=f"{prefix}_in_{i}"):
                    driver.switch_to.default_content()
                    log("[DEBUG] Cookies aceites (iframe).")
                    try:
                        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    except Exception:
                        pass
                    return True
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

        for sel in [
            "button[aria-label='Accept all']",
            "button[aria-label*='accept' i]",
            "[id*='consent' i] button",
            "[id*='cookie' i] button",
            ".qc-cmp2-summary-buttons .qc-cmp2-submit",
            "button[data-testid*='accept' i]",
        ]:
            try:
                ok = driver.execute_script(f"var el = document.querySelector('{sel}'); if(el){{ el.click(); return true; }} return false;")
                if ok:
                    log("[DEBUG] Cookies aceites via JS generic.")
                    return True
            except Exception:
                continue

        log("[DEBUG] Nenhum botão de cookies encontrado/clicado.")
        return False
    except Exception as e:
        log(f"[ERRO aceitar_cookies]: {e}")
        return False

# -------------------------------------------------------------
# Pesquisa: abrir já em Notícias (sem cliques de aba)
# -------------------------------------------------------------
def abrir_pesquisa_google(driver, keyword):
    url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl=pt-PT&gl=pt&tbm=nws"
    open_url_with_timeout(driver, url, soft_wait=0.8)
    aceitar_cookies_se_existem(driver, prefix="google_cookies_search")
    try:
        WebDriverWait(driver, 6).until(
            EC.any_of(
                EC.url_contains("tbm=nws"),
                EC.presence_of_element_located((By.XPATH, "//a[.//h3][@href]")),
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'dbsr')]//a[@href]")),
            )
        )
    except Exception:
        pass

# -------------------------------------------------------------
# Filtro de tempo (UI + fallback leve por URL)
# -------------------------------------------------------------
def aplicar_filtro_tempo(driver, filtro_tempo):
    if not filtro_tempo or not filtro_tempo.strip():
        return
    log(f"[DEBUG] A aplicar filtro de tempo: {filtro_tempo}")
    try:
        btn_ferr = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']")))
        try_click(driver, btn_ferr, prefix="ferramentas")
        time.sleep(0.6)

        btn_recent = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']")))
        try_click(driver, btn_recent, prefix="recentes")
        time.sleep(0.6)

        itens = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']")))
        alvo = None
        alvo_txt = filtro_tempo.strip().lower()
        for it in itens:
            try:
                if alvo_txt in it.text.strip().lower():
                    alvo = it
                    break
            except Exception:
                continue
        if alvo:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", alvo)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", alvo)
            time.sleep(0.8)
    except Exception as e:
        log(f"[ERRO filtro]: {e}")
    aplicar_filtro_tempo_por_url(driver, filtro_tempo)

def aplicar_filtro_tempo_por_url(driver, filtro_tempo):
    if not filtro_tempo:
        return
    t = filtro_tempo.strip().lower()
    code = None
    if "hora" in t: code = "h"
    elif "24" in t or "dia" in t: code = "d"
    elif "semana" in t: code = "w"
    elif "mês" in t or "mes" in t: code = "m"
    elif "ano" in t: code = "y"
    if not code:
        return
    try:
        p = urlparse(driver.current_url)
        qs = parse_qs(p.query)
        qs["tbs"] = [f"qdr:{code}"]
        newq = urlencode({k: (v[0] if isinstance(v, list) else v) for k, v in qs.items()})
        new_url = urlunparse((p.scheme, p.netloc, p.path, p.params, newq, p.fragment))
        open_url_with_timeout(driver, new_url, soft_wait=0.5)
        log(f"[DEBUG] Filtro aplicado por URL: tbs=qdr:{code}")
    except Exception:
        pass

def clicar_linguagem(driver):
    log("[DEBUG] A tentar definir língua (se presente)...")
    try:
        pesquisar_div = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'KTBKoe') and contains(., 'Pesquisar na Web')]"))
        )
        try_click(driver, pesquisar_div, prefix="lingua_pesquisar_na_web")
        time.sleep(0.6)

        link_pt = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Pesquisar páginas em Português')]"))
        )
        try_click(driver, link_pt, prefix="lingua_pesquisar_pt")
        time.sleep(0.8)
    except Exception as e:
        log(f"[DEBUG] Linguagem: não aplicável/visível ({e})")

# -------------------------------------------------------------
# Coleta de links em tbm=nws (mantendo a tua regra + fallbacks leves)
# -------------------------------------------------------------
def coletar_links_noticias(driver, excluir_br=False):
    log("[DEBUG] A recolher links das notícias...")
    links = []
    raw_items = []

    try:
        blocos = WebDriverWait(driver, 12).until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[@role='heading' and contains(@class,'n0jPhd')]"))
        )
        for bloco in blocos:
            try:
                a_el = bloco.find_element(By.XPATH, ".//ancestor::a[1]")
                href = a_el.get_attribute("href") or ""
                if not href:
                    continue
                raw_items.append((a_el, href))
            except Exception:
                continue
    except Exception:
        pass

    if not raw_items:
        try:
            anchors = driver.find_elements(By.XPATH, "//a[.//div[@role='heading'] or .//h3]")
            for a_el in anchors:
                try:
                    href = a_el.get_attribute("href") or ""
                    if href:
                        raw_items.append((a_el, href))
                except Exception:
                    continue
        except Exception:
            pass

    for a_el, href in raw_items:
        try:
            parsed = urlparse(href)
            domain = parsed.netloc.lower()
            if href.startswith("/"):
                href = urljoin("https://www.google.com", href)
                parsed = urlparse(href)
                domain = parsed.netloc.lower()

            if excluir_br and domain.endswith(".br"):
                continue

            data_text = "N/D"
            try:
                data_parent = a_el.find_element(By.XPATH, ".//ancestor::*[self::div or self::article][1]")
                spans = data_parent.find_elements(By.XPATH, ".//span|.//time")
                for sp in spans:
                    txt = (sp.get_attribute("aria-label") or sp.text or "").strip()
                    if not txt:
                        continue
                    if re.match(r"^há\s+\d+\s+(minuto|hora|dia|semana|m[eê]s|ano)s?$", txt, flags=re.IGNORECASE):
                        data_text = txt; break
                    if re.match(r"^\d{2}/\d{2}/\d{4}$", txt):
                        data_text = txt; break
                    if re.search(r"\d", txt) and any(w in txt.lower() for w in ("há","min","hora","dia","semana","mês","mes","ano")):
                        data_text = txt; break
            except Exception:
                pass

            links.append((href, data_text))
        except Exception:
            continue

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        save_html(driver, f"no_results_serp_{int(time.time())}.html")
    return links

# -------------------------------------------------------------
# Visitar links e voltar (memória otimizada)
# -------------------------------------------------------------
def _page_text_for_match(driver, max_chars=200_000):
    try:
        txt = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
        if len(txt) > max_chars:
            return txt[:max_chars]
        return txt
    except Exception:
        return ""

def visitar_links(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links...")

    # Limite opcional por keyword (0 = sem limite)
    if MAX_LINKS_PER_KEYWORD and len(links) > MAX_LINKS_PER_KEYWORD:
        log(f"[DEBUG] A limitar visitas a {MAX_LINKS_PER_KEYWORD} links por keyword.")
        links = links[:MAX_LINKS_PER_KEYWORD]

    results_url = driver.current_url
    kw_lower = (keyword or "").lower()
    for href_google, data_pub in links:
        try:
            try:
                link_element = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[@href='{href_google}']"))
                )
            except Exception:
                try:
                    link_element = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, f"//a[starts-with(@href, '{href_google.split('&')[0]}')]"))
                    )
                except Exception:
                    link_element = None

            if link_element is None:
                open_url_with_timeout(driver, href_google, soft_wait=0.8)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_element)
                time.sleep(0.4)
                if not try_click(driver, link_element, prefix="abrir_artigo"):
                    driver.execute_script("window.location = arguments[0];", href_google)
                time.sleep(1.0)

            try:
                aceitar_cookies_se_existem(driver, prefix="site_cookie")
            except Exception:
                pass

            texto = _page_text_for_match(driver)
            titulo = driver.title or "Sem título"
            site_name = urlparse(driver.current_url).netloc
            encontrou = kw_lower in (texto.lower() if texto else "")

            resultados.append({
                "link": driver.current_url,
                "titulo": titulo,
                "site": site_name,
                "status": "ENCONTRADA" if encontrou else "NÃO ENCONTRADA",
                "data": data_pub
            })
        except Exception as e:
            log(f"[ERRO visitar_link]: {e}")
            resultados.append({
                "link": href_google,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": str(e)
            })
        finally:
            # Voltar e limpar um pouco de estado/memória
            try:
                driver.back()
                time.sleep(0.8)
            except Exception:
                try:
                    open_url_with_timeout(driver, results_url, soft_wait=0.5)
                except Exception:
                    pass
            try:
                driver.execute_cdp_cmd("Network.clearBrowserCache", {})
                driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
                driver.execute_cdp_cmd("Performance.disable", {})
            except Exception:
                pass
            gc.collect()

# -------------------------------------------------------------
# Próxima página (preferir click; fallback por parâmetro)
# -------------------------------------------------------------
def proxima_pagina(driver):
    log("[DEBUG] Próxima página...")
    try:
        nxt = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.ID, "pnnext")))
        if try_click(driver, nxt, prefix="pnnext"):
            time.sleep(0.8)
            return True
    except Exception:
        pass

    try:
        parsed = urlparse(driver.current_url)
        qs = dict([kv for kv in [p.split("=",1) if "=" in p else (p,"") for p in parsed.query.split("&") if p]])
        start = int(qs.get("start","0") or "0")
        qs["start"] = str(start + 10)
        new_query = "&".join([f"{k}={v}" for k,v in qs.items()])
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        prev = driver.current_url
        open_url_with_timeout(driver, new_url, soft_wait=0.6)
        if driver.current_url == prev:
            log("[DEBUG] URL não mudou ao paginar — a parar.")
            return False
        return True
    except Exception:
        return False

# -------------------------------------------------------------
# Execução principal (entra diretamente em Notícias por URL)
# -------------------------------------------------------------
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (adaptação fiel).")
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")  # janela um pouco menor poupa memória
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=2")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--lang=pt-PT")
    options.add_argument(f"--user-agent={USER_AGENT}")
    # Otimizações de memória/performance sem mudar a lógica
    options.page_load_strategy = "eager"  # não espera todos os recursos
    options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2  # bloquear imagens
    })
    # Flags adicionais do patch mínimo
    options.add_argument("--incognito")
    options.add_argument("--disable-application-cache")
    options.add_argument("--disk-cache-size=0")
    options.add_argument("--media-cache-size=0")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--no-zygote")
    options.add_argument("--mute-audio")
    options.add_argument("--renderer-process-limit=1")
    options.add_argument("--disable-features=PaintHolding")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1280, 720)

    resultados = []
    try:
        open_url_with_timeout(driver, "https://www.google.com/ncr", soft_wait=0.6)
        aceitar_cookies_se_existem(driver, prefix="google_cookies_ncr")

        abrir_pesquisa_google(driver, keyword)

        aplicar_filtro_tempo(driver, filtro_tempo)
        clicar_linguagem(driver)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='heading']"))
            )
        except Exception:
            pass

        page_count = 0
        while True:
            links = coletar_links_noticias(driver, excluir_br=False)
            if links:
                visitar_links(driver, links, keyword, resultados)

            page_count += 1
            if MAX_PAGES_PER_KEYWORD and page_count >= MAX_PAGES_PER_KEYWORD:
                log(f"[DEBUG] A parar por limite de páginas: {page_count}/{MAX_PAGES_PER_KEYWORD}")
                break

            if not proxima_pagina(driver):
                break
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        gc.collect()

    return resultados

def rodar_scraper_sequencial(keywords_string, filtro_tempo):
    all_results = []
    keywords = [kw.strip() for kw in keywords_string.split(",") if kw.strip()]
    for kw in keywords:
        log(f"[DEBUG] A processar keyword: '{kw}'")
        try:
            res = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(res)
        except Exception as e:
            log(f"[ERRO ao processar '{kw}']: {type(e).__name__}: {str(e)}")
            all_results.append({"keyword": kw, "erro": f"{type(e).__name__}: {str(e)}"})
        finally:
            gc.collect()
    return all_results

if __name__ == "__main__":
    ensure_dirs()
    log("Script iniciado.")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas', 'Última semana', 'Último mês', 'Último ano'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))