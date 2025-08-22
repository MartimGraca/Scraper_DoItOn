import os
import re
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

# ========================= Config =========================
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
PAGELOAD_TIMEOUT = 25
SCRIPT_TIMEOUT = 20
WAIT_SHORT = 0.2

HL = "pt-PT"
GL = "pt"

# Para replicar o log e evitar timeouts, por omissão não visita os links
VISIT_LINKS = False

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

    try:
        driver.execute_script("""
            var overlays = document.querySelectorAll(
              'div[role=dialog], .modal, .overlay, .popup, [aria-hidden="true"], .fc-dialog-container, #onetrust-banner-sdk'
            );
            overlays.forEach(o=>{ try{ o.style.display='none'; o.remove(); }catch(e){} });
        """)
        time.sleep(WAIT_SHORT)
        driver.execute_script("arguments[0].click();", el)
        save_shot(driver, f"{prefix}_after_overlays_{ts}.png")
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

# ===================== Pesquisa/Notícias ====================
def abrir_pesquisa_google(driver, keyword):
    url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl={HL}&gl={GL}"
    open_url_with_timeout(driver, url, soft_wait=1.0)
    aceitar_cookies_se_existem(driver, prefix="google_cookies_search")

def _esperar_entrar_em_noticias(driver, timeout=8):
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.url_contains("tbm=nws"),
                EC.presence_of_element_located((By.XPATH, "//a[.//h3][@href]")),
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'dbsr')]//a[@href]")),
            )
        )
        return True
    except Exception:
        return False

def clicar_noticias_tab(driver):
    log("[DEBUG] A clicar no separador Notícias...")
    selectors = [
        "//a[contains(@href,'tbm=nws')]",
        "//a[normalize-space()='Notícias']",
        "//a[@aria-label='Notícias']",
        "//div[@role='tablist']//a[normalize-space()='Notícias']",
        "//a//span[normalize-space()='Notícias']/ancestor::a[1]",
    ]
    for xp in selectors:
        try:
            el = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, xp)))
            if try_click(driver, el, prefix="tab_noticias_xpath"):
                if _esperar_entrar_em_noticias(driver, timeout=8):
                    return True
        except Exception:
            continue

    # JS direto
    try:
        ok = driver.execute_script("""
            var a = document.querySelector("a[href*='tbm=nws']");
            if(a){ a.click(); return true; } return false;
        """)
        if ok and _esperar_entrar_em_noticias(driver, timeout=8):
            return True
    except Exception:
        pass

    # Classe específica (caso exista)
    try:
        ok = driver.execute_script("""
            var els = document.getElementsByClassName('sc-4ed1b0a0-5 gUqbJK');
            if(els && els.length){ try{ els[0].click(); return true; }catch(e){} }
            return false;
        """)
        if ok and _esperar_entrar_em_noticias(driver, timeout=8):
            return True
    except Exception:
        pass

    return False

def ir_para_noticias_por_url(driver, keyword):
    # Fallback leve por URL
    url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl={HL}&gl={GL}&tbm=nws"
    log("[DEBUG] A forçar 'Notícias' por URL (tbm=nws).")
    open_url_with_timeout(driver, url, soft_wait=1.0)
    _esperar_entrar_em_noticias(driver, timeout=6)

def aplicar_filtro_tempo(driver, filtro_tempo):
    if not filtro_tempo or not filtro_tempo.strip():
        return False
    log(f"[DEBUG] A aplicar filtro de tempo: {filtro_tempo}")
    try:
        btn_ferr = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']")))
        try_click(driver, btn_ferr, prefix="ferramentas")
        time.sleep(0.6)

        btn_recent = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']")))
        try_click(driver, btn_recent, prefix="recentes")
        time.sleep(0.6)

        itens = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']")))
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
    except Exception as e:
        log(f"[ERRO filtro]: {e}")
    return False

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
        open_url_with_timeout(driver, new_url, soft_wait=0.8)
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
          // procurar data perto
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
      // tentar shadow roots básicos
      try {
        document.querySelectorAll('*').forEach(el=>{
          try{ if(el.shadowRoot){ el.shadowRoot.querySelectorAll('a[href]').forEach(add); } }catch(e){}
        });
      } catch(e){}
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

    # Espera por resultados e faz lazy-load leve
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[@href and (starts-with(@href,'http') or starts-with(@href,'/url'))]"))
        )
    except Exception:
        pass
    for _ in range(2):
        try:
            driver.execute_script("window.scrollBy(0, Math.max(900, window.innerHeight*0.9));")
        except Exception:
            pass
        time.sleep(0.7)

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

    # Fallback adicional com XPaths típicos dos cartões de notícias
    if not links:
        try:
            anchors = driver.find_elements(By.XPATH, "//div[contains(@class,'dbsr')]//a[@href] | //a[.//div[@role='heading']][@href] | //a[.//h3][@href]")
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

# =================== Visitar links (opcional) ==========================
def visitar_links(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links...")
    if not VISIT_LINKS:
        return  # não visita; apenas replica o log
    results_url = driver.current_url
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
                open_url_with_timeout(driver, href_google, soft_wait=1.0)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_element)
                time.sleep(0.4)
                if not try_click(driver, link_element, prefix="abrir_artigo"):
                    driver.execute_script("window.location = arguments[0];", href_google)
                time.sleep(1.2)

            titulo = driver.title or "Sem título"
            resultados.append({"link": driver.current_url, "titulo": titulo, "data": data_pub})
        except Exception as e:
            log(f"[ERRO visitar_link]: {e}")
            save_shot(driver, f"erro_visitar_link_{int(time.time())}.png")
        finally:
            try:
                driver.back()
                time.sleep(0.9)
            except Exception:
                try:
                    open_url_with_timeout(driver, results_url, soft_wait=0.8)
                except Exception:
                    pass

# =================== Execução principal =======================
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (adaptação fiel).")
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
    options.add_argument("--lang=" + HL)
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1366, 768)

    resultados = []
    try:
        open_url_with_timeout(driver, "https://www.google.com/ncr", soft_wait=0.8)
        aceitar_cookies_se_existem(driver, prefix="google_cookies_ncr")

        abrir_pesquisa_google(driver, keyword)

        if not clicar_noticias_tab(driver):
            ir_para_noticias_por_url(driver, keyword)

        ok_ui = aplicar_filtro_tempo(driver, filtro_tempo)
        if not ok_ui:
            aplicar_filtro_tempo_por_url(driver, filtro_tempo)

        clicar_linguagem(driver)

        links = coletar_links_noticias(driver, excluir_br=False)
        if links:
            visitar_links(driver, links, keyword, resultados)
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