import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urlunparse, urljoin, urlencode, parse_qs

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# ========================= Config =========================
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
PAGELOAD_TIMEOUT = 25
SCRIPT_TIMEOUT = 20
WAIT_SHORT = 0.2
WAIT_MED = 0.6

HL = "pt-PT"
GL = "pt"

# Limites de segurança para paginação
MAX_PAGES = 20

# ========================= Utils ==========================
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

def open_url_with_timeout(driver, url, timeout=PAGELOAD_TIMEOUT, soft_wait=1.0):
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
    ts = int(time.time())
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(WAIT_SHORT)
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
    return False

def normalize_google_href(href, base="https://www.google.com"):
    try:
        if href.startswith("/"):
            return urljoin(base, href)
        return href
    except Exception:
        return href

# ========================= Cookies =========================
def aceitar_cookies_se_existem(driver, prefix="cookies"):
    try:
        log("[DEBUG] A tentar aceitar cookies...")
        time.sleep(0.5)
        candidatos = [
            "//button//div[normalize-space(text())='Aceitar tudo']",
            "//button[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
            "//div[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
            "//span[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
            "//button[contains(@aria-label, 'Accept')]",
        ]
        # fora de iframes
        for xp in candidatos:
            try:
                el = driver.find_element(By.XPATH, xp)
                if el and try_click(driver, el, prefix=f"{prefix}_out"):
                    return True
            except Exception:
                pass
        # iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for i, fr in enumerate(iframes):
            try:
                driver.switch_to.frame(fr)
                time.sleep(0.2)
                for xp in candidatos:
                    try:
                        el = driver.find_element(By.XPATH, xp)
                        if el and try_click(driver, el, prefix=f"{prefix}_in_{i}"):
                            driver.switch_to.default_content()
                            return True
                    except Exception:
                        pass
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
        log("[DEBUG] Nenhum botão de cookies encontrado/clicado.")
        return False
    except Exception as e:
        log(f"[ERRO aceitar_cookies]: {e}")
        return False

# ===================== Pesquisa/Notícias ====================
def pesquisar_por_input(driver, keyword):
    # Logs explícitos de cada etapa
    log("[DEBUG] A abrir a página inicial e a clicar na barra de pesquisa...")
    open_url_with_timeout(driver, "https://www.google.com/ncr", soft_wait=0.8)
    aceitar_cookies_se_existem(driver, prefix="google_cookies_home")

    # Possíveis seletores do input
    inputs = [
        (By.NAME, "q"),
        (By.CSS_SELECTOR, "input[aria-label='Pesquisar']"),
        (By.CSS_SELECTOR, "input[type='search']"),
        (By.CSS_SELECTOR, "textarea[name='q']"),
    ]

    el = None
    for by, sel in inputs:
        try:
            el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((by, sel)))
            break
        except Exception:
            continue

    if not el:
        log("[DEBUG] Não consegui focar o input de pesquisa — vou pesquisar por URL direta (fallback).")
        url = f"https://www.google.com/search?q={keyword}&hl={HL}&gl={GL}"
        open_url_with_timeout(driver, url, soft_wait=1.0)
        return

    try:
        try_click(driver, el, prefix="focus_search_input")
    except Exception:
        pass

    try:
        el.clear()
    except Exception:
        pass

    log(f"[DEBUG] A escrever a keyword no input: '{keyword}'")
    for ch in keyword:
        el.send_keys(ch)
        time.sleep(0.05)
    el.send_keys(Keys.ENTER)
    time.sleep(1.0)

def ir_para_noticias_por_click(driver):
    log("[DEBUG] A tentar clicar em 'Notícias' (UI).")
    selectors = [
        "//a[contains(@href,'tbm=nws')]",
        "//a[normalize-space()='Notícias']",
        "//a[@aria-label='Notícias']",
        "//div[@role='tablist']//a[normalize-space()='Notícias']",
        "//a//span[normalize-space()='Notícias']/ancestor::a[1]",
    ]
    for xp in selectors:
        try:
            el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
            if try_click(driver, el, prefix="tab_noticias"):
                time.sleep(1.0)
                return True
        except Exception:
            continue
    return False

def ir_para_noticias_por_url(driver):
    try:
        p = urlparse(driver.current_url)
        qs = parse_qs(p.query)
        qs["tbm"] = ["nws"]
        qs["hl"] = [HL]
        qs["gl"] = [GL]
        newq = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
        new_url = urlunparse((p.scheme, p.netloc, p.path, p.params, newq, p.fragment))
        log("[DEBUG] A forçar 'Notícias' por URL (tbm=nws).")
        open_url_with_timeout(driver, new_url, soft_wait=1.0)
        return True
    except Exception as e:
        log(f"[ERRO ir_para_noticias_por_url]: {e}")
        return False

def map_filtro_para_qdr(filtro_tempo):
    if not filtro_tempo:
        return None
    t = filtro_tempo.strip().lower()
    if "hora" in t:
        return "h"   # última hora
    if "24" in t or "dia" in t:
        return "d"   # último dia
    if "semana" in t:
        return "w"
    if "mês" in t or "mes" in t:
        return "m"
    if "ano" in t:
        return "y"
    return None

def aplicar_filtro_tempo_por_click(driver, filtro_tempo):
    if not filtro_tempo or not filtro_tempo.strip():
        return True
    log(f"[DEBUG] A aplicar filtro pela UI: {filtro_tempo}")
    try:
        ferr = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']")))
        if not try_click(driver, ferr, prefix="ferramentas"):
            return False
        time.sleep(0.6)
        recent = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']")))
        if not try_click(driver, recent, prefix="recentes"):
            return False
        time.sleep(0.6)

        # Submenu
        itens = WebDriverWait(driver, 8).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']"))
        )
        alvo_txt = filtro_tempo.strip().lower()
        for it in itens:
            try:
                if alvo_txt in (it.text or "").strip().lower():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", it)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", it)
                    time.sleep(0.8)
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        log(f"[ERRO aplicar_filtro_tempo_por_click]: {e}")
        return False

def aplicar_filtro_tempo_por_url(driver, filtro_tempo):
    code = map_filtro_para_qdr(filtro_tempo)
    if not code:
        return False
    try:
        p = urlparse(driver.current_url)
        qs = parse_qs(p.query)
        qs["tbs"] = [f"qdr:{code}"]
        newq = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
        new_url = urlunparse((p.scheme, p.netloc, p.path, p.params, newq, p.fragment))
        open_url_with_timeout(driver, new_url, soft_wait=1.0)
        log(f"[DEBUG] Filtro aplicado por URL: tbs=qdr:{code}")
        return True
    except Exception as e:
        log(f"[ERRO aplicar_filtro_tempo_por_url]: {e}")
        return False

def clicar_linguagem(driver):
    log("[DEBUG] A tentar definir língua (se presente)...")
    try:
        pesquisar_div = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'KTBKoe') and contains(., 'Pesquisar na Web')]"))
        )
        try_click(driver, pesquisar_div, prefix="lingua_pesquisar_na_web")
        time.sleep(0.6)
        link_pt = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Pesquisar páginas em Português')]"))
        )
        try_click(driver, link_pt, prefix="lingua_pesquisar_pt")
        time.sleep(0.8)
    except Exception:
        pass

def esperar_resultados_noticias(driver):
    # Esperar por qualquer um dos cartões/âncoras típicos
    try:
        WebDriverWait(driver, 10).until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'dbsr')]//a[@href]")),
                EC.presence_of_element_located((By.XPATH, "//a[contains(@class,'WlydOe')][@href]")),
                EC.presence_of_element_located((By.XPATH, "//a[contains(@class,'tHmfQe')][@href]")),
                EC.presence_of_element_located((By.XPATH, "//a[.//h3][@href]")),
                EC.presence_of_element_located((By.XPATH, "//a[.//div[@role='heading']][@href]")),
            )
        )
    except Exception:
        pass
    # 2 scrolls leves para lazy-load
    for _ in range(2):
        try:
            driver.execute_script("window.scrollBy(0, Math.max(700, window.innerHeight*0.8));")
        except Exception:
            pass
        time.sleep(0.7)

# ===================== Coleta de links ======================
def js_coletar_links_deep(driver):
    js = r"""
    return (function(){
      const out = []; const seen = new Set();
      function add(a){
        try{
          const hrefRaw = a.getAttribute('href')||'';
          if(!hrefRaw) return;
          if(!(hrefRaw.startsWith('http') || hrefRaw.startsWith('/url'))) return;
          const hrefAbs = hrefRaw.startsWith('/') ? new URL(hrefRaw, location.origin).href : hrefRaw;
          if(seen.has(hrefAbs)) return;
          seen.add(hrefAbs);
          let container = a.closest('div.dbsr, article, div.SoaBEf, div.Gx5Zad, div.MBeuO, div.UFQHwe') || a.parentElement || a;
          let dateTxt = '';
          if(container){
            let t = container.querySelector('time');
            if(t) dateTxt = (t.getAttribute('aria-label')||t.textContent||'').trim();
            if(!dateTxt){
              let s = container.querySelector('span');
              if(s) dateTxt = (s.getAttribute('aria-label')||s.textContent||'').trim();
            }
          }
          out.push({href: hrefAbs, date: dateTxt});
        }catch(e){}
      }
      // anchors no documento
      document.querySelectorAll('a[href]').forEach(add);
      // tentar atravessar shadow roots básicos
      document.querySelectorAll('*').forEach(el=>{
        try{
          if(el.shadowRoot){
            el.shadowRoot.querySelectorAll('a[href]').forEach(add);
          }
        }catch(e){}
      });
      return out;
    })();
    """
    try:
        items = driver.execute_script(js)
        return items or []
    except Exception:
        return []

def coletar_links_noticias(driver, excluir_br=False):
    log("[DEBUG] A recolher links das notícias...")
    links = []
    seen = set()

    # 3 tentativas com scroll leve + deep JS
    for attempt in range(3):
        if attempt > 0:
            try:
                driver.execute_script("window.scrollBy(0, Math.max(900, window.innerHeight*0.9));")
            except Exception:
                pass
            time.sleep(0.9)

        items = js_coletar_links_deep(driver)
        for it in items:
            try:
                href = it.get("href") or ""
                if not href:
                    continue
                if excluir_br and href.startswith("http"):
                    dom = urlparse(href).netloc.lower()
                    if dom.endswith(".br"):
                        continue
                data_text = "N/D"
                dt = (it.get("date") or "").strip()
                if re.match(r"^há\s+\d+\s+(minuto|hora|dia|semana|m[eê]s|ano)s?$", dt, flags=re.IGNORECASE) or \
                   re.match(r"^\d{2}/\d{2}/\d{4}$", dt) or \
                   (re.search(r"\d", dt) and any(w in dt.lower() for w in ("há","min","hora","dia","semana","mês","mes","ano"))):
                    data_text = dt
                if href not in seen:
                    seen.add(href)
                    links.append((href, data_text))
            except Exception:
                continue
        if links:
            break

    # Fallback simples via XPath se deep falhar totalmente
    if not links:
        try:
            anchors = driver.find_elements(By.XPATH, "//div[contains(@class,'dbsr')]//a[@href] | //a[.//h3][@href] | //a[.//div[@role='heading']][@href]")
        except Exception:
            anchors = []
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                if not href:
                    continue
                if excluir_br and href.startswith("http"):
                    dom = urlparse(href).netloc.lower()
                    if dom.endswith(".br"):
                        continue
                links.append((href, "N/D"))
            except Exception:
                continue

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        save_shot(driver, f"no_results_serp_{int(time.time())}.png")
        save_html(driver, f"no_results_serp_{int(time.time())}.html")
    return links

# =================== Visitar links ==========================
def visitar_links(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links...")
    results_url = driver.current_url
    for href_google, data_pub in links:
        try:
            # tentar clicar o mesmo <a> do SERP
            link_element = None
            try:
                link_element = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[@href='{href_google}']"))
                )
            except Exception:
                try:
                    base = href_google.split("&")[0].replace("'", "\\'")
                    link_element = WebDriverWait(driver, 4).until(
                        EC.element_to_be_clickable((By.XPATH, f"//a[starts-with(@href, '{base}')]"))
                    )
                except Exception:
                    link_element = None

            if link_element:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_element)
                time.sleep(0.4)
                if not try_click(driver, link_element, prefix="abrir_artigo"):
                    driver.execute_script("window.location = arguments[0];", normalize_google_href(href_google))
            else:
                open_url_with_timeout(driver, normalize_google_href(href_google), soft_wait=1.0)

            time.sleep(1.2)
            try:
                aceitar_cookies_se_existem(driver, prefix="site_cookie")
            except Exception:
                pass

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
            site_name = urlparse(driver.current_url).netloc
            encontrou = keyword.lower() in corpo.lower()
            resultados.append({
                "link": driver.current_url,
                "titulo": titulo,
                "site": site_name,
                "status": "ENCONTRADA" if encontrou else "NÃO ENCONTRADA",
                "data": data_pub
            })
        except Exception as e:
            log(f"[ERRO visitar_link]: {e}")
            save_shot(driver, f"erro_visitar_link_{int(time.time())}.png")
            resultados.append({
                "link": href_google,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": str(e)
            })
        finally:
            try:
                driver.back()
                time.sleep(0.9)
            except Exception:
                try:
                    open_url_with_timeout(driver, results_url, soft_wait=0.8)
                except Exception:
                    pass

# =================== Paginação ==============================
def proxima_pagina(driver, page_no, prev_url):
    log("[DEBUG] Próxima página...")
    # 1) tentar clicar pnnext
    try:
        nxt = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.ID, "pnnext")))
        if try_click(driver, nxt, prefix="pnnext"):
            time.sleep(1.0)
            return True
    except Exception:
        pass

    # 2) fallback por URL start=*
    try:
        p = urlparse(driver.current_url)
        qs = parse_qs(p.query)
        start = int((qs.get("start", ["0"])[0]) or "0")
        qs["start"] = [str(start + 10)]
        newq = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
        new_url = urlunparse((p.scheme, p.netloc, p.path, p.params, newq, p.fragment))
        open_url_with_timeout(driver, new_url, soft_wait=0.8)
        # parar se URL não mudou (fim) ou se excedeu limite de páginas
        if driver.current_url == prev_url:
            log("[DEBUG] URL não mudou após tentar próxima página — a parar.")
            return False
        if page_no + 1 >= MAX_PAGES:
            log("[DEBUG] Limite de páginas atingido — a parar.")
            return False
        return True
    except Exception:
        return False

# =================== Runner principal =======================
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (Notícias + Ferramentas/Recentes).")

    options = uc.ChromeOptions()
    # Para depurar visualmente, comente a linha abaixo
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=2")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--lang=" + HL)
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1366, 768)

    resultados = []
    try:
        # Pesquisa pela barra (com logs) e fallback por URL se necessário
        pesquisar_por_input(driver, keyword)

        # Ir para Notícias (clique → URL fallback)
        if not ir_para_noticias_por_click(driver):
            log("[DEBUG] Falha a clicar 'Notícias' — a ir por URL (tbm=nws).")
            if not ir_para_noticias_por_url(driver):
                save_shot(driver, f"no_news_tab_{int(time.time())}.png")
                save_html(driver, f"no_news_tab_{int(time.time())}.html")
                return resultados

        esperar_resultados_noticias(driver)

        # Filtro (UI → URL fallback)
        ok_ui = aplicar_filtro_tempo_por_click(driver, filtro_tempo)
        if not ok_ui:
            log("[DEBUG] Filtro pela UI falhou — a aplicar pela URL.")
            aplicar_filtro_tempo_por_url(driver, filtro_tempo)

        clicar_linguagem(driver)
        esperar_resultados_noticias(driver)

        # Loop de páginas com travão de “duas seguidas sem links”
        zero_streak = 0
        page_no = 0
        while True:
            prev_url = driver.current_url
            links = coletar_links_noticias(driver, excluir_br=False)

            if not links:
                zero_streak += 1
            else:
                zero_streak = 0
                visitar_links(driver, links, keyword, resultados)

            if zero_streak >= 2:
                log("[DEBUG] Duas páginas seguidas sem links — a parar.")
                break

            if not proxima_pagina(driver, page_no, prev_url):
                break

            page_no += 1

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return resultados

def rodar_scraper_sequencial(keywords_string, filtro_tempo):
    ensure_dirs()
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
    log("Script iniciado.")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas', 'Última semana', 'Último mês', 'Último ano'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))