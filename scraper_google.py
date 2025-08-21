import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, quote_plus, urlunparse, unquote

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
MAX_PAGES = 5
PAGELOAD_TIMEOUT = 25
SCRIPT_TIMEOUT = 20
ARTICLE_SOFT_WAIT = 3
EXCLUIR_DOMINIOS_BR = False  # põe True se quiseres excluir .br

# -------------------- Utilitários --------------------
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

def wait_ready_quick(driver, timeout=10):
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

# -------------------- Cliques (cookies) --------------------
def try_click_strategies(driver, element, prefix="click"):
    ts = int(time.time())
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.15)
    except Exception:
        pass
    try:
        ActionChains(driver).move_to_element(element).pause(0.05).click(element).perform()
        save_shot(driver, f"{prefix}_action_{ts}.png")
        return True
    except Exception:
        pass
    try:
        element.click()
        save_shot(driver, f"{prefix}_selenium_{ts}.png")
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_js_{ts}.png")
        return True
    except Exception:
        pass
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
        time.sleep(0.4)
        textos = ['Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Consent', 'Agree', 'OK', 'Aceitar cookies', 'Aceitar todos']
        btn = localizar_botao_por_textos(driver, textos)
        if btn and try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_out"):
            log("[DEBUG] Cookies aceites (fora iframe).")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            return True
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
        for sel in [
            "document.querySelector('button[aria-label=\"Accept all\"]')",
            "document.querySelector('button[aria-label*=\"accept\" i]')",
            "document.querySelector('[id*=\"consent\" i] button')",
            "document.querySelector('[id*=\"cookie\" i] button')",
            "document.querySelector('.qc-cmp2-summary-buttons .qc-cmp2-submit')",
            "document.querySelector('button[data-testid*=\"accept\" i]')",
        ]:
            ok = driver.execute_script(f"var el = {sel}; if(el){{ el.click(); return true; }} return false;")
            if ok:
                log("[DEBUG] Cookies aceites via JS generic.")
                return True
        log("[DEBUG] Nenhum botão de cookies encontrado/clicado.")
        return False
    except Exception as e:
        log(f"[ERRO aceitar_cookies]: {e}")
        return False

# -------------------- Pesquisa por URL (tbm=nws) --------------------
def map_time_filter_qdr(filtro_tempo: str) -> str:
    if not filtro_tempo: return ""
    f = filtro_tempo.strip().lower()
    if "hora" in f: return "h"
    if "24" in f or "dia" in f: return "d"
    if "semana" in f: return "w"
    if "mês" in f or "mes" in f: return "m"
    if "ano" in f: return "y"
    return ""

def build_google_news_search_url(keyword: str, filtro_tempo: str, hl="pt-PT", gl="pt", lr=None) -> str:
    q = quote_plus(keyword)
    qdr = map_time_filter_qdr(filtro_tempo)
    params = {"q": q, "tbm": "nws", "hl": hl, "gl": gl}
    if lr: params["lr"] = lr  # por defeito None para não restringir demasiado
    if qdr: params["tbs"] = f"qdr:{qdr}"
    return "https://www.google.com/search?" + urlencode(params)

def next_page_url(current_url: str) -> str | None:
    try:
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query)
        current_start = int(qs.get("start", ["0"])[0])
        qs["start"] = [str(current_start + 10)]
        new_query = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except Exception:
        return None

def extract_final_url(href: str) -> str:
    try:
        parsed = urlparse(href)
        if "google." in parsed.netloc and parsed.path == "/url":
            qs = parse_qs(parsed.query)
            for key in ("url", "q"):
                if key in qs and qs[key]:
                    return unquote(qs[key][0])
        return href
    except Exception:
        return href

# -------------------- Navegação --------------------
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
    wait_ready_quick(driver, timeout=min(soft_wait, 8))
    time.sleep(max(0.2, soft_wait - 1))

# -------------------- Coleta robusta via JS (tbm=nws) --------------------
def collect_links_tbm_nws_js(driver):
    """
    Coleta robusta de links em tbm=nws:
    - .dbsr cards
    - anchors que contêm h3
    - anchors que contêm [role=heading]
    - classes frequentes WlydOe, tHmfQe
    - fallback anchors http dentro de #search
    Resolve /url? e remove google links/duplicados.
    """
    js = r"""
    (function(){
      function extractFinal(u){
        try{
          const p = new URL(u, location.href);
          if (p.hostname.includes('google.') && p.pathname === '/url'){
            const v = p.searchParams.get('url') || p.searchParams.get('q');
            if (v) return decodeURIComponent(v);
          }
          return p.href;
        }catch(e){ return u; }
      }

      // candidatos por prioridade
      const sets = [];
      sets.push(Array.from(document.querySelectorAll("div#search div.dbsr a[href]")));
      sets.push(Array.from(document.querySelectorAll("div#search a:has(h3)")));
      sets.push(Array.from(document.querySelectorAll("div#search a:has([role='heading'])")));
      sets.push(Array.from(document.querySelectorAll("div#search a.WlydOe[href]")));
      sets.push(Array.from(document.querySelectorAll("div#search a.tHmfQe[href]")));
      sets.push(Array.from(document.querySelectorAll("div#search a[href^='http']")));

      const seen = new Set();
      for (const arr of sets){
        const out = [];
        for (const a of arr){
          try{
            const href = a.getAttribute('href') || '';
            if (!href || !href.startsWith('http')) continue;
            const finalHref = extractFinal(href);
            if (!finalHref.startsWith('http')) continue;
            const host = (new URL(finalHref)).hostname.toLowerCase();
            if (host.includes('google.') || host.includes('webcache.googleusercontent')) continue;
            if (seen.has(finalHref)) continue;
            seen.add(finalHref);

            // heurística de data próxima
            let dataText = "N/D";
            try{
              let container = a.closest('div,article') || a;
              const spans = container.querySelectorAll('span,time');
              for (const s of spans){
                const t = (s.getAttribute('aria-label') || s.textContent || '').trim();
                if (!t) continue;
                const low = t.toLowerCase();
                if (/^há\s+\d+\s+(minuto|hora|dia|semana|m[eê]s|ano)s?$/i.test(t)) { dataText = t; break; }
                if (/\d/.test(t) && (low.includes('há')||low.includes('min')||low.includes('hora')||low.includes('dia')||low.includes('semana')||low.includes('mês')||low.includes('mes')||low.includes('ano'))) { dataText = t; break; }
                if (/^\d{2}\/\d{2}\/\d{4}$/.test(t)) { dataText = t; break; }
              }
            }catch(e){}
            out.push([finalHref, dataText]);
          }catch(e){}
        }
        if (out.length) return out; // devolve à primeira lista com resultados
      }
      return [];
    })();
    """
    try:
        results = driver.execute_script(js)
        if not results:
            return []
        # results é lista de [href, data]
        cleaned = []
        seen = set()
        for href, data_text in results:
            try:
                dom = urlparse(href).netloc.lower()
                if EXCLUIR_DOMINIOS_BR and dom.endswith(".br"):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                cleaned.append((href, data_text or "N/D"))
            except Exception:
                continue
        return cleaned
    except Exception as e:
        log(f"[ERRO JS coleta]: {e}")
        return []

def coletar_links_tbm_nws(driver):
    log("[DEBUG] A recolher links (tbm=nws, robusto JS + scroll)...")
    links = []
    # espera container
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "search")))
    except Exception:
        pass

    # até 5 ciclos: coleta + scroll + pausa
    last_len = -1
    for i in range(5):
        batch = collect_links_tbm_nws_js(driver)
        if batch:
            links = batch
            break
        # scroll para tentar carregar blocos
        try:
            driver.execute_script("window.scrollBy(0, Math.max(600, window.innerHeight*0.8));")
        except Exception:
            pass
        time.sleep(0.6)
        # pequena pausa adicional
        time.sleep(0.4)
        # proteção contra loops vazios
        if len(batch) == last_len:
            time.sleep(0.5)
        last_len = len(batch)

    log(f"[DEBUG] {len(links)} links recolhidos (tbm=nws).")
    if not links:
        save_shot(driver, f"no_results_tbm_{int(time.time())}.png")
        save_html(driver, f"no_results_tbm_{int(time.time())}.html")
    return links

# -------------------- Visitar artigos --------------------
def visitar_links_mesma_aba(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links na MESMA aba...")
    results_url_for_return = driver.current_url
    for url, data_pub in links:
        try:
            open_url_with_timeout(driver, url)
            # cookies do site
            try:
                aceitar_cookies_se_existem(driver, screenshot_prefix="site_cookie")
            except Exception:
                pass
            # recolha conteúdo
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
            # regressar por URL (sem back)
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
    log("[DEBUG] A iniciar o scraper do Google (headless, tbm=nws apenas).")
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
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1366, 768)

    resultados = []
    try:
        # Fixar .com e aceitar cookies
        open_url_with_timeout(driver, "https://www.google.com/ncr", timeout=PAGELOAD_TIMEOUT, soft_wait=2)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies_ncr")

        # Abrir tbm=nws com filtro qdr
        start_url = build_google_news_search_url(keyword, filtro_tempo, hl="pt-PT", gl="pt", lr=None)
        log(f"[DEBUG] Start URL (tbm=nws): {start_url}")
        open_url_with_timeout(driver, start_url, timeout=PAGELOAD_TIMEOUT, soft_wait=2)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies")

        page_count = 0
        while True:
            page_count += 1
            links = coletar_links_tbm_nws(driver)
            if links:
                visitar_links_mesma_aba(driver, links, keyword, resultados)

            if page_count >= MAX_PAGES:
                log("[DEBUG] Limite de páginas atingido (tbm=nws).")
                break

            nxt = next_page_url(driver.current_url)
            if not nxt:
                log("[DEBUG] Sem próxima página (tbm=nws).")
                break
            open_url_with_timeout(driver, nxt, timeout=PAGELOAD_TIMEOUT, soft_wait=2)
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
    log("Script iniciado (headless, tbm=nws apenas).")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas', 'Última semana', 'Último mês', 'Último ano'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))