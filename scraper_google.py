import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, quote_plus, urlunparse, urljoin, unquote

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Configs
HEADLESS = True
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
MAX_PAGES = 5             # limite de páginas de resultados
PAGELOAD_TIMEOUT = 20     # segs por navegação
SCRIPT_TIMEOUT = 20       # segs para JS
ARTICLE_SOFT_WAIT = 3     # segs de “respiração” após abrir artigo
EXCLUIR_DOMINIOS_BR = False  # define True se quiseres excluir sites .br

# -------------------- Utilitários de logging/screenshot --------------------
def ensure_dirs():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def now_str():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    ensure_dirs()
    line = f"[{now_str()}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def save_shot(driver, name):
    ensure_dirs()
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        driver.save_screenshot(path)
        log(f"[DEBUG] Screenshot guardada: {path}")
    except Exception as e:
        log(f"[DEBUG] Falhou guardar screenshot ({e})")

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

def wait_ready_quick(driver, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        try:
            state = driver.execute_script("return document.readyState")
            if state in ("interactive", "complete"):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def wait_selector_visible(driver, by, selector, timeout=8):
    try:
        WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, selector)))
        return True
    except Exception:
        return False

# -------------------- Cliques de apoio (para cookies) --------------------
def try_click_strategies(driver, element, prefix="click"):
    ts = int(time.time())
    # viewport
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.15)
    except Exception:
        pass
    # ActionChains
    try:
        ActionChains(driver).move_to_element(element).pause(0.05).click(element).perform()
        save_shot(driver, f"{prefix}_action_{ts}.png")
        return True
    except Exception:
        pass
    # element.click
    try:
        element.click()
        save_shot(driver, f"{prefix}_selenium_{ts}.png")
        return True
    except Exception:
        pass
    # JS click
    try:
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_js_{ts}.png")
        return True
    except Exception:
        pass
    # elementFromPoint
    try:
        success = driver.execute_script("""
            var el = arguments[0];
            if (!el) return false;
            var r = el.getBoundingClientRect();
            var x = Math.floor(r.left + r.width/2);
            var y = Math.floor(r.top + r.height/2);
            var t = document.elementFromPoint(x, y);
            if (t) { t.click(); return true; }
            return false;
        """, element)
        save_shot(driver, f"{prefix}_frompoint_{ts}.png")
        if success:
            return True
    except Exception:
        pass
    # remover overlays e tentar
    try:
        driver.execute_script("""
            var overlays = document.querySelectorAll(
                'div[role=dialog], .modal, .overlay, .popup, [aria-hidden="true"], .fc-dialog-container, #onetrust-banner-sdk'
            );
            overlays.forEach(function(o){ try{ o.style.display='none'; o.remove(); }catch(e){} });
        """)
        time.sleep(0.2)
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_after_overlays_{ts}.png")
        return True
    except Exception:
        pass
    return False

# -------------------- Cookies --------------------
def localizar_botao_por_textos(driver, textos):
    lower = [t.lower() for t in textos]
    xpaths = []
    for txt in lower:
        x = f"contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{txt}')"
        xpaths.extend([
            f"//button[{x}]",
            f"//a[{x}]",
            f"//span[{x}]",
            f"//div[{x}]",
            f"//input[@type='button' and contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{txt}')]",
        ])
    for xp in xpaths:
        try:
            elems = driver.find_elements(By.XPATH, xp)
            for e in elems:
                try:
                    if e.is_displayed() and e.is_enabled():
                        return e
                except Exception:
                    continue
        except Exception:
            continue
    return None

def aceitar_cookies_se_existem(driver, screenshot_prefix="cookies"):
    try:
        log("[DEBUG] A tentar aceitar cookies...")
        time.sleep(0.5)
        textos = ['Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Consent', 'Agree', 'OK', 'Aceitar cookies', 'Aceitar todos']
        # Fora de iframes
        btn = localizar_botao_por_textos(driver, textos)
        if btn and try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_out"):
            log("[DEBUG] Cookies aceites (fora iframe).")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            return True
        # Dentro de iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for idx, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                time.sleep(0.2)
                btn = localizar_botao_por_textos(driver, textos)
                if btn and try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_in_{idx}"):
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
        # JS genérico
        js_candidates = [
            "document.querySelector('button[aria-label=\"Accept all\"]')",
            "document.querySelector('button[aria-label*=\"accept\" i]')",
            "document.querySelector('[id*=\"consent\" i] button')",
            "document.querySelector('[id*=\"cookie\" i] button')",
            "document.querySelector('.qc-cmp2-summary-buttons .qc-cmp2-submit')",
            "document.querySelector('button[data-testid*=\"accept\" i]')",
        ]
        for i, sel in enumerate(js_candidates):
            ok = driver.execute_script(f"var el = {sel}; if(el){{ el.click(); return true; }} return false;")
            if ok:
                log("[DEBUG] Cookies aceites via JS generic.")
                return True
        log("[DEBUG] Nenhum botão de cookies encontrado/clicado.")
        return False
    except Exception as e:
        log(f"[ERRO aceitar_cookies]: {e}")
        return False

# -------------------- Pesquisa (por URL, sem input) --------------------
def map_time_filter(filtro_tempo: str) -> str:
    if not filtro_tempo:
        return ""
    f = filtro_tempo.strip().lower()
    if "hora" in f:
        return "h"      # última hora
    if "24" in f or "dia" in f:
        return "d"      # últimas 24 horas
    if "semana" in f:
        return "w"
    if "mês" in f or "mes" in f:
        return "m"
    if "ano" in f:
        return "y"
    return ""

def build_google_news_url(keyword: str, filtro_tempo: str, hl="pt-PT", gl="pt", lr=None) -> str:
    # lr=None por defeito para não restringir demasiado (pode reduzir a 0 resultados)
    q = quote_plus(keyword)
    qdr = map_time_filter(filtro_tempo)
    params = {
        "q": q,
        "tbm": "nws",
        "hl": hl,
        "gl": gl,
    }
    if lr:
        params["lr"] = lr
    if qdr:
        params["tbs"] = f"qdr:{qdr}"
    return "https://www.google.com/search?" + urlencode(params)

def get_next_results_page_url(current_url: str) -> str | None:
    try:
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query)
        current_start = int(qs.get("start", ["0"])[0])
        qs["start"] = [str(current_start + 10)]
        new_query = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except Exception:
        return None

def extract_final_url(possible_google_url: str) -> str:
    """Resolve href quando vem como /url? ou link do Google para link externo final."""
    try:
        parsed = urlparse(possible_google_url)
        if "google." in parsed.netloc and parsed.path == "/url":
            qs = parse_qs(parsed.query)
            # ordem de preferência
            for key in ("url", "q"):
                if key in qs and qs[key]:
                    return unquote(qs[key][0])
        return possible_google_url
    except Exception:
        return possible_google_url

# -------------------- Coleta e visita --------------------
def coletar_links_noticias(driver):
    log("[DEBUG] A recolher links das notícias...")
    links = []

    # Espera por evidência de resultados no #search
    try:
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.ID, "search")))
    except Exception:
        pass
    time.sleep(0.4)

    # Estratégias de seleção (em ordem)
    strategies = [
        ("css", "div.dbsr a"),  # markup clássico tbm=nws
        ("xpath", "//div[@id='search']//a[.//h3]"),  # anchor com h3
        ("xpath", "//div[@id='search']//a[.//div[@role='heading']]"),  # anchor com role=heading
        ("css", "div#search a"),  # fallback: todos os links em #search
    ]

    seen = set()

    for kind, sel in strategies:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel) if kind == "css" else driver.find_elements(By.XPATH, sel)
        except Exception:
            elems = []
        for a in elems:
            try:
                href = a.get_attribute("href") or ""
                if not href.startswith("http"):
                    continue
                final_href = extract_final_url(href)
                if not final_href.startswith("http"):
                    continue
                # filtrar links google e duplicados
                dom = urlparse(final_href).netloc.lower()
                if "google." in dom:
                    continue
                if EXCLUIR_DOMINIOS_BR and dom.endswith(".br"):
                    continue
                if final_href in seen:
                    continue

                # tentar encontrar "data" relativa no cartão
                data_text = "N/D"
                try:
                    card = a
                    # subir a um container próximo
                    try:
                        card = a.find_element(By.XPATH, "./ancestor::*[self::div or self::article][1]")
                    except Exception:
                        pass
                    spans = card.find_elements(By.XPATH, ".//span")
                    for s in spans:
                        t = s.text.strip()
                        # heurística: contém dígitos ou palavras de tempo ('há', 'min', 'hora', 'dia', 'semana', 'mês', 'ano')
                        if re.search(r"\d", t) or any(w in t.lower() for w in ("há", "min", "hora", "dia", "semana", "mês", "mes", "ano")):
                            data_text = t
                            break
                except Exception:
                    pass

                seen.add(final_href)
                links.append((final_href, data_text))
            except Exception:
                continue

        if links:
            break  # já encontrámos via uma estratégia

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        save_shot(driver, f"no_results_{int(time.time())}.png")
        save_html(driver, f"no_results_{int(time.time())}.html")
    return links

def open_url_with_timeout(driver, url, timeout=PAGELOAD_TIMEOUT, soft_wait=ARTICLE_SOFT_WAIT):
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    except WebDriverException as e:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        raise e
    wait_ready_quick(driver, timeout=min(soft_wait, 6))
    time.sleep(max(0.2, soft_wait - 1))

def visitar_links_mesma_aba(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links na MESMA aba...")
    results_url_for_return = driver.current_url
    for url, data_pub in links:
        try:
            open_url_with_timeout(driver, url)
            # Cookies do site
            try:
                aceitar_cookies_se_existem(driver, screenshot_prefix="site_cookie")
            except Exception:
                pass
            # Recolher texto
            corpo = ""
            try:
                artigos = driver.find_elements(By.TAG_NAME, "article")
                if artigos:
                    corpo = " ".join([a.text for a in artigos if a.text.strip()])
                else:
                    divs = driver.find_elements(By.XPATH, "//div[contains(@class,'content') or contains(@class,'article')]")
                    corpo = " ".join([d.text for d in divs if d.text.strip()])
                if not corpo:
                    corpo = driver.page_source
            except Exception:
                corpo = driver.page_source
            titulo = driver.title or "Sem título"
            site_name = urlparse(url).netloc
            encontrou = keyword.lower() in corpo.lower()
            resultados.append({
                "link": url,
                "titulo": titulo,
                "site": site_name,
                "status": "ENCONTRADA" if encontrou else "NÃO ENCONTRADA",
                "data": data_pub
            })
        except Exception as e:
            log(f"[ERRO visitar_link]: {e}")
            save_shot(driver, f"erro_visitar_link_{int(time.time())}.png")
            resultados.append({
                "link": url,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": str(e)
            })
        finally:
            # Regressa SEM back() (evita hangs), sempre por URL
            try:
                open_url_with_timeout(driver, results_url_for_return, timeout=PAGELOAD_TIMEOUT, soft_wait=2)
            except Exception as e:
                log(f"[DEBUG] Falha ao regressar à página de resultados: {e}")
                try:
                    driver.get(results_url_for_return)
                except Exception:
                    pass
            time.sleep(0.2)

# -------------------- Execução --------------------
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (headless, sem interagir com input).")
    options = uc.ChromeOptions()
    # Headless por flags
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1024")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=2")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--blink-settings=imagesEnabled=false")  # acelera e evita bloqueios com imagens
    options.add_argument(f"--user-agent={USER_AGENT}")
    # Carregamento não bloqueante
    options.set_capability("pageLoadStrategy", "none")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1280, 1024)

    resultados = []
    try:
        # Fixar .com e aceitar cookies do Google
        open_url_with_timeout(driver, "https://www.google.com/ncr", timeout=PAGELOAD_TIMEOUT, soft_wait=2)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies_ncr")

        # Ir diretamente para resultados de Notícias com filtros aplicados
        start_url = build_google_news_url(keyword, filtro_tempo)
        log(f"[DEBUG] Start URL: {start_url}")
        open_url_with_timeout(driver, start_url, timeout=PAGELOAD_TIMEOUT, soft_wait=2)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies")

        page_count = 0
        while True:
            page_count += 1
            links = coletar_links_noticias(driver)
            if links:
                visitar_links_mesma_aba(driver, links, keyword, resultados)
            if page_count >= MAX_PAGES:
                log("[DEBUG] Limite de páginas atingido.")
                break
            next_url = get_next_results_page_url(driver.current_url)
            if not next_url:
                log("[DEBUG] Sem próxima página.")
                break
            open_url_with_timeout(driver, next_url, timeout=PAGELOAD_TIMEOUT, soft_wait=2)
            time.sleep(0.2)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
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
    return all_results

if __name__ == "__main__":
    ensure_dirs()
    log("Script iniciado (headless, sem input).")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas', 'Última semana', 'Último mês', 'Último ano'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))