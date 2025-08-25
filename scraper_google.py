import os
import re
import gc
import json
import time
from datetime import datetime
from urllib.parse import urlparse, urlunparse, urljoin, parse_qs, urlencode, quote_plus

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# -------------------------------------------------------------
# Configurações principais
# -------------------------------------------------------------
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
PAGELOAD_TIMEOUT = 20
SCRIPT_TIMEOUT = 15
WAIT_SHORT = 0.15

# Limites/agressividade (podem ser ajustados por env)
MAX_LINKS_PER_KEYWORD = int(os.getenv("MAX_LINKS_PER_KEYWORD", "40") or "40")
MAX_PAGES_PER_KEYWORD = int(os.getenv("MAX_PAGES_PER_KEYWORD", "5") or "5")
MAX_SECONDS_PER_LINK = int(os.getenv("MAX_SECONDS_PER_LINK", "15") or "15")
MAX_SECONDS_PER_KEYWORD = int(os.getenv("MAX_SECONDS_PER_KEYWORD", "40") or "40")  # 0 = sem limite
FAST_MODE = int(os.getenv("FAST_MODE", "1") or "1")  # 1 = fazer tudo o mais rápido/curto possível
DO_NOT_ACCEPT_SITE_COOKIES = int(os.getenv("DO_NOT_ACCEPT_SITE_COOKIES", "1") or "1")  # 1 = não aceitar cookies nos sites
RESULTS_JSONL_PATH = os.getenv("RESULTS_JSONL_PATH", "").strip()  # se vazio, acumula em memória

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

def save_shot(driver, name):
    return

def save_html(driver, name):
    # Mantido apenas para diagnóstico quando não há resultados
    ensure_dirs()
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        html = driver.page_source
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"[DEBUG] HTML dump guardado: {path}")
    except Exception as e:
        log(f"[DEBUG] Falhou guardar HTML dump ({e})")

def open_url_with_timeout(driver, url, timeout=PAGELOAD_TIMEOUT, soft_wait=0.5):
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
    # Mantemos a util; mas vamos abrir artigos sempre por URL (ver visitar_links)
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

# -------------------------------------------------------------
# Cookies (Google apenas; sites destino opcionalmente ignorado)
# -------------------------------------------------------------
from selenium.webdriver.common.keys import Keys as SeleniumKeys

def localizar_botao_por_textos(driver, textos, deadline=None):
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
        if deadline and time.time() > deadline:
            return None
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

def aceitar_cookies_google(driver, time_budget_s=3):
    start = time.time()
    deadline = start + max(1, time_budget_s)
    try:
        log("[DEBUG] A tentar aceitar cookies...")
        textos = ['Aceitar tudo','Accept all','Aceitar','Concordo','Consent','Agree','OK','Aceitar cookies','Aceitar todos']
        btn = localizar_botao_por_textos(driver, textos, deadline)
        if btn and try_click(driver, btn, prefix="cookies_out"):
            log("[DEBUG] Cookies aceites (fora iframe).")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(SeleniumKeys.ESCAPE)
            except Exception:
                pass
            return True

        # iframes (sem ultrapassar orçamento)
        if time.time() < deadline:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i, fr in enumerate(iframes):
                if time.time() > deadline:
                    break
                try:
                    driver.switch_to.frame(fr)
                    time.sleep(0.12)
                    btn = localizar_botao_por_textos(driver, textos, deadline)
                    if btn and try_click(driver, btn, prefix=f"cookies_in_{i}"):
                        driver.switch_to.default_content()
                        log("[DEBUG] Cookies aceites (iframe).")
                        try:
                            driver.find_element(By.TAG_NAME, "body").send_keys(SeleniumKeys.ESCAPE)
                        except Exception:
                            pass
                        return True
                    driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()

        # JS direto (rápido)
        for sel in [
            "button[aria-label='Accept all']",
            "button[aria-label*='accept' i]",
            "[id*='consent' i] button",
            "[id*='cookie' i] button",
            ".qc-cmp2-summary-buttons .qc-cmp2-submit",
            "button[data-testid*='accept' i]",
        ]:
            if time.time() > deadline:
                break
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
# Pesquisa: já abre em Notícias (sem cliques)
# -------------------------------------------------------------
def abrir_pesquisa_google(driver, keyword):
    url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl=pt-PT&gl=pt&tbm=nws"
    open_url_with_timeout(driver, url, soft_wait=0.5)
    aceitar_cookies_google(driver, time_budget_s=(3 if FAST_MODE else 6))
    try:
        WebDriverWait(driver, 5).until(
            EC.any_of(
                EC.url_contains("tbm=nws"),
                EC.presence_of_element_located((By.XPATH, "//div[@role='heading']")),
            )
        )
    except Exception:
        pass

# -------------------------------------------------------------
# Filtro de tempo: só por URL (removida tentativa via UI)
# -------------------------------------------------------------
def aplicar_filtro_tempo_por_url(driver, filtro_tempo):
    t = (filtro_tempo or "").strip().lower()
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
        open_url_with_timeout(driver, new_url, soft_wait=0.4)
        log(f"[DEBUG] Filtro aplicado por URL: tbs=qdr:{code}")
    except Exception:
        pass

# -------------------------------------------------------------
# Recolha de links
# -------------------------------------------------------------
def coletar_links_noticias(driver, excluir_br=False):
    log("[DEBUG] A recolher links das notícias...")
    links = []
    raw_items = []
    try:
        blocos = WebDriverWait(driver, 8).until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[@role='heading' and contains(@class,'n0jPhd')]"))
        )
        for bloco in blocos:
            try:
                a_el = bloco.find_element(By.XPATH, ".//ancestor::a[1]")
                href = a_el.get_attribute("href") or ""
                if href:
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
            if href.startswith("/"):
                href = urljoin("https://www.google.com", href)
            if excluir_br and urlparse(href).netloc.lower().endswith(".br"):
                continue

            # Tentar apanhar data relativa
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

    if MAX_LINKS_PER_KEYWORD and len(links) > MAX_LINKS_PER_KEYWORD:
        links = links[:MAX_LINKS_PER_KEYWORD]

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        save_html(driver, f"no_results_serp_{int(time.time())}.html")
    return links

# -------------------------------------------------------------
# Escrita imediata de resultados (JSONL opcional)
# -------------------------------------------------------------
def write_result_immediately(result):
    if not RESULTS_JSONL_PATH:
        return False
    try:
        os.makedirs(os.path.dirname(RESULTS_JSONL_PATH), exist_ok=True)
    except Exception:
        pass
    try:
        with open(RESULTS_JSONL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        log(f"[DEBUG] Falha a escrever JSONL: {e}")
        return False

# -------------------------------------------------------------
# Visitar links (abrir por URL; limpeza agressiva a cada link)
# -------------------------------------------------------------
def _page_text_for_match(driver, max_chars=80_000):
    try:
        txt = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
        if len(txt) > max_chars:
            return txt[:max_chars]
        return txt
    except Exception:
        return ""

def _hard_clean_page(driver):
    # Limpa o máximo de estado possível entre links para baixar picos de memória
    try:
        driver.execute_script("try{localStorage.clear();}catch(e){}; try{sessionStorage.clear();}catch(e){};")
    except Exception:
        pass
    try:
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})
        driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
        driver.execute_cdp_cmd("Performance.disable", {})
    except Exception:
        pass
    gc.collect()

def visitar_links(driver, links, keyword, resultados, results_url):
    log(f"[DEBUG] A visitar {len(links)} links...")
    kw_lower = (keyword or "").lower()

    for idx, (href_google, data_pub) in enumerate(links, start=1):
        inicio_link = time.time()
        try:
            dominio = urlparse(href_google).netloc or "google"
            log(f"[DEBUG] ({idx}/{len(links)}) Abrir: {dominio}")

            # Abrir diretamente por URL para evitar interações no SERP
            open_url_with_timeout(driver, href_google, soft_wait=0.4)

            # Opcional: não aceitar cookies nos sites destino para poupar memória/tempo
            if not DO_NOT_ACCEPT_SITE_COOKIES:
                aceitar_cookies_google(driver, time_budget_s=(3 if FAST_MODE else 6))

            # Timeout duro por link
            if time.time() - inicio_link > MAX_SECONDS_PER_LINK:
                result = {
                    "link": driver.current_url,
                    "titulo": "Timeout",
                    "site": urlparse(driver.current_url).netloc,
                    "status": "ERRO",
                    "data": data_pub,
                    "erro": f"TIMEOUT {int(time.time()-inicio_link)}s"
                }
                resultados.append(result)
                write_result_immediately(result)
                log(f"[DEBUG] ({idx}/{len(links)}) TIMEOUT após {int(time.time()-inicio_link)}s.")
            else:
                texto = _page_text_for_match(driver)
                titulo = driver.title or "Sem título"
                site_name = urlparse(driver.current_url).netloc
                encontrou = kw_lower in (texto.lower() if texto else "")

                result = {
                    "link": driver.current_url,
                    "titulo": titulo,
                    "site": site_name,
                    "status": "ENCONTRADA" if encontrou else "NÃO ENCONTRADA",
                    "data": data_pub
                }
                resultados.append(result)
                write_result_immediately(result)
                log(f"[DEBUG] ({idx}/{len(links)}) {site_name} | {'ENCONTRADA' if encontrou else 'NÃO ENCONTRADA'} | {int(time.time()-inicio_link)}s")

        except Exception as e:
            result = {
                "link": href_google,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": str(e)
            }
            resultados.append(result)
            write_result_immediately(result)
            log(f"[ERRO visitar_link] ({idx}/{len(links)}): {e}")
        finally:
            # Libertar DOM pesado antes de voltar aos resultados
            try:
                driver.get("about:blank")
                time.sleep(0.2)
            except Exception:
                pass
            _hard_clean_page(driver)
            # Voltar aos resultados
            try:
                open_url_with_timeout(driver, results_url, soft_wait=0.3)
            except Exception:
                pass

# -------------------------------------------------------------
# Paginação (mantida, mas com limites agressivos)
# -------------------------------------------------------------
def proxima_pagina(driver):
    log("[DEBUG] Próxima página...")
    try:
        parsed = urlparse(driver.current_url)
        qs_pairs = [p for p in parsed.query.split("&") if p]
        qs = dict([kv if "=" in (kv := p.split("=",1)) else (p,"") for p in qs_pairs])
        start = int(qs.get("start","0") or "0")
        qs["start"] = str(start + 10)
        new_query = "&".join([f"{k}={v}" for k,v in qs.items()])
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        prev = driver.current_url
        open_url_with_timeout(driver, new_url, soft_wait=0.4)
        if driver.current_url == prev:
            log("[DEBUG] URL não mudou ao paginar — a parar.")
            return False
        return True
    except Exception:
        return False

# -------------------------------------------------------------
# Execução principal
# -------------------------------------------------------------
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (adaptação fiel).")
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1120,640")  # janela menor
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=2")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--lang=pt-PT")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.page_load_strategy = "eager"
    options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2  # bloquear imagens
    })
    # Flags para reduzir footprint
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
    driver.set_window_size(1120, 640)

    resultados = []
    try:
        open_url_with_timeout(driver, "https://www.google.com/ncr", soft_wait=0.4)
        aceitar_cookies_google(driver, time_budget_s=(3 if FAST_MODE else 6))

        abrir_pesquisa_google(driver, keyword)
        aplicar_filtro_tempo_por_url(driver, filtro_tempo)

        try:
            WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='heading']"))
            )
        except Exception:
            pass

        total_links_processados = 0
        page_count = 0
        keyword_deadline = (time.time() + MAX_SECONDS_PER_KEYWORD) if MAX_SECONDS_PER_KEYWORD else None

        while True:
            if keyword_deadline and time.time() > keyword_deadline:
                log(f"[DEBUG] A parar por tempo total da keyword (>{MAX_SECONDS_PER_KEYWORD}s).")
                break

            links = coletar_links_noticias(driver, excluir_br=False)
            if links:
                # Respeitar MAX_LINKS_PER_KEYWORD total
                if MAX_LINKS_PER_KEYWORD:
                    links = links[:max(0, MAX_LINKS_PER_KEYWORD - total_links_processados)]
                results_url = driver.current_url
                visitar_links(driver, links, keyword, resultados, results_url)
                total_links_processados += len(links)

            page_count += 1
            if MAX_PAGES_PER_KEYWORD and page_count >= MAX_PAGES_PER_KEYWORD:
                log(f"[DEBUG] A parar por limite de páginas: {page_count}/{MAX_PAGES_PER_KEYWORD}")
                break
            if MAX_LINKS_PER_KEYWORD and total_links_processados >= MAX_LINKS_PER_KEYWORD:
                log(f"[DEBUG] Atingido limite de links: {total_links_processados}/{MAX_LINKS_PER_KEYWORD}")
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
            # Se estivermos a gravar JSONL, não precisamos acumular; mas devolvemos os últimos resultados para a UI
            if RESULTS_JSONL_PATH:
                all_results.extend(res[-3:])  # manter leve: só últimos N
            else:
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