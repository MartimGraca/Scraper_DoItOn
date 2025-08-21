import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, quote_plus, urlunparse, unquote, urljoin

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Tentamos usar BeautifulSoup; se não existir, fazemos fallback simples
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

import requests

# Configs
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
MAX_PAGES = 5
PAGELOAD_TIMEOUT = 25
SCRIPT_TIMEOUT = 20
REQUEST_TIMEOUT = 25
ARTICLE_SOFT_WAIT = 2.0
EXCLUIR_DOMINIOS_BR = False  # True para excluir .br nos resultados

# -------------------- Utilitários de logging --------------------
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

def save_html_text(text, name):
    ensure_dirs()
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        log(f"[DEBUG] HTML dump guardado: {path}")
    except Exception as e:
        log(f"[DEBUG] Falhou guardar HTML dump ({e})")

# -------------------- Selenium helpers --------------------
def open_url_with_timeout(driver, url, timeout=PAGELOAD_TIMEOUT, soft_wait=ARTICLE_SOFT_WAIT):
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

def localizar_botao_por_textos(driver, textos):
    lower = [t.lower() for t in textos]
    xpaths = []
    for txt in lower:
        cond = f"contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{txt}')"
        xpaths.extend([
            f"//button[{cond}]",
            f"//a[{cond}]",
            f"//div[{cond}]",
            f"//span[{cond}]",
            f"//input[@type='button' and contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{txt}')]",
        ])
    for xp in xpaths:
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

def try_click(driver, el, prefix="click"):
    ts = int(time.time())
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.15)
    except Exception:
        pass
    try:
        ActionChains(driver).move_to_element(el).pause(0.05).click(el).perform()
        save_shot(driver, f"{prefix}_action_{ts}.png")
        return True
    except Exception:
        pass
    try:
        el.click()
        save_shot(driver, f"{prefix}_selenium_{ts}.png")
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", el)
        save_shot(driver, f"{prefix}_js_{ts}.png")
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
        time.sleep(0.2)
        driver.execute_script("arguments[0].click();", el)
        save_shot(driver, f"{prefix}_after_overlays_{ts}.png")
        return True
    except Exception:
        pass
    return False

def aceitar_cookies_se_existem(driver, prefix="cookies"):
    try:
        log("[DEBUG] A tentar aceitar cookies...")
        time.sleep(0.4)
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
        # JS genérico
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

# -------------------- Requests helpers --------------------
def build_tbm_nws_url(keyword: str, filtro_tempo: str, hl="pt-PT", gl="pt", lr=None, start=0) -> str:
    q = quote_plus(keyword)
    params = {"q": q, "tbm": "nws", "hl": hl, "gl": gl}
    # filtro de tempo
    f = (filtro_tempo or "").strip().lower()
    qdr = ""
    if "hora" in f: qdr = "h"
    elif "24" in f or "dia" in f: qdr = "d"
    elif "semana" in f: qdr = "w"
    elif "mês" in f or "mes" in f: qdr = "m"
    elif "ano" in f: qdr = "y"
    if qdr:
        params["tbs"] = f"qdr:{qdr}"
    if lr:
        params["lr"] = lr
    if start:
        params["start"] = str(start)
    return "https://www.google.com/search?" + urlencode(params)

def selenium_get_google_cookies(driver):
    # devolve cookies de .google.com num dict name->value
    jar = {}
    try:
        for c in driver.get_cookies():
            dom = (c.get("domain") or "").lower()
            if "google." in dom:
                jar[c["name"]] = c["value"]
    except Exception:
        pass
    return jar

def make_requests_session(google_cookies: dict):
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    })
    # cookies do Google (CONSENT, NID, 1P_JAR, etc.)
    for k, v in (google_cookies or {}).items():
        s.cookies.set(k, v, domain=".google.com")
    return s

def resolve_google_url(href: str) -> str:
    try:
        if not href:
            return ""
        if href.startswith("/"):
            href = urljoin("https://www.google.com", href)
        p = urlparse(href)
        if "google." in p.netloc and p.path == "/url":
            qs = parse_qs(p.query)
            for key in ("url", "q"):
                if key in qs and qs[key]:
                    return unquote(qs[key][0])
        return href
    except Exception:
        return href or ""

# -------------------- Parsing HTML dos resultados --------------------
def parse_news_results_html(html: str):
    links = []
    seen = set()

    def add_link(href, container):
        nonlocal links, seen
        try:
            final = resolve_google_url(href)
            if not final.startswith("http"):
                return
            dom = urlparse(final).netloc.lower()
            if "google." in dom or "webcache.googleusercontent" in dom:
                return
            if EXCLUIR_DOMINIOS_BR and dom.endswith(".br"):
                return
            if final in seen:
                return
            # extrair data relativa
            data_text = "N/D"
            if container is not None:
                # tentar <time> e <span>
                times = container.find_all("time") if hasattr(container, "find_all") else []
                for t in times:
                    tt = (t.get("aria-label") or t.get_text() or "").strip()
                    if tt:
                        data_text = tt
                        break
                if data_text == "N/D":
                    spans = container.find_all("span") if hasattr(container, "find_all") else []
                    for s in spans:
                        txt = (s.get_text() or "").strip()
                        if not txt:
                            continue
                        if re.match(r"^há\s+\d+\s+(minuto|hora|dia|semana|m[eê]s|ano)s?$", txt, flags=re.IGNORECASE):
                            data_text = txt; break
                        if re.match(r"^\d{2}/\d{2}/\d{4}$", txt):
                            data_text = txt; break
                        if re.search(r"\d", txt) and any(w in txt.lower() for w in ("há","min","hora","dia","semana","mês","mes","ano")):
                            data_text = txt; break
            seen.add(final)
            links.append((final, data_text))
        except Exception:
            return

    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")

        # Estratégias (por prioridade)
        strategies = [
            ("css", "div.dbsr a"),
            ("css", "a.WlydOe"),
            ("css", "a.tHmfQe"),
            ("h3", None),  # âncoras que contêm h3
            ("role_heading", None),  # âncoras com [role=heading]
            ("fallback", "a"),  # todos os anchors
        ]

        for kind, sel in strategies:
            found_any = False
            try:
                if kind == "css":
                    anchors = soup.select(sel)
                    for a in anchors:
                        href = a.get("href") or ""
                        if not href:
                            continue
                        container = a.find_parent(["div","article","section","span"]) or a
                        add_link(href, container)
                    found_any = len(links) > 0
                elif kind == "h3":
                    anchors = soup.find_all("a")
                    for a in anchors:
                        if a.find("h3") is not None:
                            href = a.get("href") or ""
                            if not href:
                                continue
                            container = a.find_parent(["div","article","section","span"]) or a
                            add_link(href, container)
                    found_any = len(links) > 0
                elif kind == "role_heading":
                    anchors = soup.find_all("a")
                    for a in anchors:
                        # procurar um descendente com role=heading
                        descendant_has_role = False
                        for d in a.descendants:
                            try:
                                # alguns parsers não preservam atributos 'role'
                                if getattr(d, "attrs", None) and d.attrs.get("role","") == "heading":
                                    descendant_has_role = True
                                    break
                            except Exception:
                                pass
                        if descendant_has_role:
                            href = a.get("href") or ""
                            if not href:
                                continue
                            container = a.find_parent(["div","article","section","span"]) or a
                            add_link(href, container)
                    found_any = len(links) > 0
                elif kind == "fallback":
                    anchors = soup.select(sel)
                    for a in anchors:
                        href = a.get("href") or ""
                        if not href:
                            continue
                        # aceitar também /url? relativo
                        if not (href.startswith("http") or href.startswith("/url")):
                            continue
                        container = a.find_parent(["div","article","section","span"]) or a
                        add_link(href, container)
                    found_any = len(links) > 0
            except Exception:
                continue

            if found_any:
                break
    else:
        # Fallback simplista sem BeautifulSoup: regex por âncoras /url? ou http
        try:
            for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I|re.S):
                href = m.group(1)
                inner = m.group(2) or ""
                if not (href.startswith("http") or href.startswith("/url")):
                    continue
                if not (re.search(r"<h3\b", inner, flags=re.I) or re.search(r'role\s*=\s*"heading"', inner, flags=re.I) or "dbsr" in inner or "WlydOe" in inner or "tHmfQe" in inner):
                    # demasiado permissivo? deixa passar — filtragem depois
                    pass
                add_link(href, None)
        except Exception:
            pass

    return links

# -------------------- Visitar artigos --------------------
def extract_text_from_html(html: str) -> str:
    text = ""
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        # tentar zonas típicas primeiro
        zones = []
        zones.extend(soup.find_all("article"))
        if not zones:
            zones = soup.select("div[class*='content'], div[class*='article'], main")
        if zones:
            text = " ".join(z.get_text(" ", strip=True) for z in zones)
        if not text:
            text = soup.get_text(" ", strip=True)
    else:
        # remove tags grosseiramente
        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I|re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I|re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text

def visitar_artigo_requests_then_selenium(url, keyword, resultados, driver=None):
    status = "NÃO ENCONTRADA"
    titulo = ""
    corpo = ""
    data_pub = None  # preenchido no chamador quando existir
    site_name = urlparse(url).netloc

    # 1) tentar com requests
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/",
        }
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.ok:
            html = r.text or ""
            corpo = extract_text_from_html(html)
            # título simples
            m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I|re.S)
            titulo = (m.group(1).strip() if m else "") if not BeautifulSoup else (BeautifulSoup(html, "html.parser").title.string.strip() if BeautifulSoup(html, "html.parser").title else "")
    except Exception:
        pass

    # 2) se corpo curto/duvidoso e temos driver, tentar Selenium (aceitar cookies do site)
    if (not corpo or len(corpo) < 200) and driver is not None:
        try:
            open_url_with_timeout(driver, url, soft_wait=1.5)
            try:
                aceitar_cookies_se_existem(driver, prefix="site_cookie")
            except Exception:
                pass
            time.sleep(0.6)
            # recolha
            try:
                arts = driver.find_elements(By.TAG_NAME, "article")
                if arts:
                    corpo = " ".join([a.text for a in arts if a.text.strip()])
                else:
                    divs = driver.find_elements(By.XPATH, "//div[contains(@class,'content') or contains(@class,'article')]")
                    corpo = " ".join([d.text for d in divs if d.text.strip()])
                if not corpo:
                    corpo = driver.page_source
            except Exception:
                corpo = driver.page_source
            try:
                titulo = driver.title or titulo
            except Exception:
                pass
        except Exception as e:
            log(f"[DEBUG] Selenium falhou a abrir artigo: {e}")

    if corpo and keyword and keyword.lower() in corpo.lower():
        status = "ENCONTRADA"

    return {
        "link": url,
        "titulo": titulo or "Sem título",
        "site": site_name,
        "status": status,
    }

# -------------------- Execução principal --------------------
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (tbm=nws com parsing server-side).")

    # 1) Abrir UC apenas para obter cookies e aceitar consent
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=2")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--lang=pt-PT")
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1366, 768)

    resultados = []
    try:
        open_url_with_timeout(driver, "https://www.google.com/ncr", soft_wait=1.0)
        aceitar_cookies_se_existem(driver, prefix="google_cookies_ncr")

        google_cookies = selenium_get_google_cookies(driver)
        sess = make_requests_session(google_cookies)

        total_links = 0
        for page_idx in range(MAX_PAGES):
            start = page_idx * 10
            url = build_tbm_nws_url(keyword, filtro_tempo, hl="pt-PT", gl="pt", lr=None, start=start)
            log(f"[DEBUG] GET tbm=nws page {page_idx+1}: {url}")
            try:
                r = sess.get(url, timeout=REQUEST_TIMEOUT)
                html = r.text or ""
                if r.status_code != 200 or not html:
                    log(f"[DEBUG] HTTP {r.status_code} sem conteúdo.")
                    # fallback: usar Selenium só para obter o HTML da página
                    try:
                        open_url_with_timeout(driver, url, soft_wait=1.2)
                        html = driver.page_source or ""
                    except Exception:
                        html = ""
                # Guardar dump se vazio
                links = parse_news_results_html(html)
                if page_idx == 0 and not links:
                    save_html_text(html, f"no_results_tbm_requests_{int(time.time())}.html")
                log(f"[DEBUG] {len(links)} links recolhidos nesta página.")
                total_links += len(links)

                # Visitar artigos (requests -> selenium fallback on-demand)
                for final_url, data_pub in links:
                    item = visitar_artigo_requests_then_selenium(final_url, keyword, resultados, driver=driver)
                    item["data"] = data_pub
                    resultados.append(item)

                # break se não há próxima (sem links ou menos de 10 itens é sinal de fim)
                if len(links) < 8:
                    break
            except Exception as e:
                log(f"[ERRO GET tbm=nws]: {e}")
                # tentar seguir mesmo assim
                continue

        if total_links == 0:
            log("[DEBUG] 0 links no tbm=nws com requests; verificar HTML dump gerado.")

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
    log("Script iniciado (tbm=nws com parsing server-side).")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas', 'Última semana', 'Último mês', 'Último ano'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))