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

# Removido: screenshots para acelerar (no-op)
def save_shot(driver, name):
    return

# Mantido: HTML dump só quando não há links (opcional e raro). Se quiseres remover também, torna no-op.
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
        # deixamos seguir; página pode ter carregado parcialmente
    # pequena “respiração” (reduzida para acelerar)
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

    # Remover overlays e tentar JS click
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
    # Mantemos o href “do Google” para clicar no SERP (como no teu código).
    # Apenas normalizamos relativo para absoluto para guardares/depurares se precisares.
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
        # Fora iframes
        btn = localizar_botao_por_textos(driver, textos)
        if btn and try_click(driver, btn, prefix=f"{prefix}_out"):
            log("[DEBUG] Cookies aceites (fora iframe).")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass
            return True

        # Dentro iframes
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

        # JS direto
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
# Passos Google: pesquisa -> tab Notícias -> filtros -> linguagem
# -------------------------------------------------------------
def abrir_pesquisa_google(driver, keyword):
    # Evita send_keys no input; abre resultados diretamente
    url = f"https://www.google.com/search?q={keyword}&hl=pt-PT&gl=pt"
    open_url_with_timeout(driver, url, soft_wait=0.8)
    aceitar_cookies_se_existem(driver, prefix="google_cookies_search")

def _esperar_entrar_em_noticias(driver, timeout=6):
    try:
        WebDriverWait(driver, timeout).until(
            EC.any_of(
                EC.url_contains("tbm=nws"),
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'dbsr')]//a[@href]")),
                EC.presence_of_element_located((By.XPATH, "//a[.//h3][@href]")),
            )
        )
        return True
    except Exception:
        return False

def clicar_noticias_tab(driver):
    log("[DEBUG] A clicar no separador Notícias...")

    # 1) Seletores habituais
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
                if _esperar_entrar_em_noticias(driver, timeout=6):
                    return True
        except Exception:
            continue

    # 2) JS direto no link com tbm=nws
    try:
        ok = driver.execute_script("""
            var a = document.querySelector("a[href*='tbm=nws']");
            if(a){ a.click(); return true; } return false;
        """)
        if ok:
            if _esperar_entrar_em_noticias(driver, timeout=6):
                log("[DEBUG] Notícias clicado via JS querySelector tbm=nws.")
                return True
    except Exception:
        pass

    # 3) Classe específica
    try:
        ok = driver.execute_script("""
            var els = document.getElementsByClassName('sc-4ed1b0a0-5 gUqbJK');
            if(els && els.length){ try{ els[0].click(); return true; }catch(e){} }
            return false;
        """)
        if ok:
            if _esperar_entrar_em_noticias(driver, timeout=6):
                log("[DEBUG] Notícias clicado via getElementsByClassName('sc-4ed1b0a0-5 gUqbJK').")
                return True
    except Exception:
        pass

    # 4) JS por texto visível “Notícias”
    try:
        ok = driver.execute_script("""
            var as = Array.from(document.querySelectorAll('a, button'));
            var alvo = as.find(n => (n.textContent||'').trim().toLowerCase() === 'notícias');
            if(alvo){ try{ alvo.click(); return true; }catch(e){} }
            return false;
        """)
        if ok:
            if _esperar_entrar_em_noticias(driver, timeout=6):
                log("[DEBUG] Notícias clicado via texto visível (JS).")
                return True
    except Exception:
        pass

    log("[DEBUG] Não consegui clicar em 'Notícias' com os métodos disponíveis.")
    return False

# --------- Fallback leve: entrar em Notícias por URL (mantendo o resto igual) ---------
def ir_para_noticias_por_url(driver, keyword):
    url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl=pt-PT&gl=pt&tbm=nws"
    log("[DEBUG] A forçar 'Notícias' por URL (tbm=nws).")
    open_url_with_timeout(driver, url, soft_wait=0.8)
    _esperar_entrar_em_noticias(driver, timeout=6)

# --------- Fallback leve: filtro de tempo por URL (tbs=qdr:*) ---------
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

    # Tua regra principal
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

    # Fallbacks suaves se a regra principal não apanhou nada
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

    # Processar, filtrar e extrair datas como no teu
    for a_el, href in raw_items:
        try:
            parsed = urlparse(href)
            domain = parsed.netloc.lower()
            # Alguns hrefs podem vir relativos "/url?..." — normalizar só para logging/visita direta
            if href.startswith("/"):
                href = urljoin("https://www.google.com", href)
                parsed = urlparse(href)
                domain = parsed.netloc.lower()

            if excluir_br and domain.endswith(".br"):
                continue

            # data
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

            # Guardamos o href “do Google” para clicar no SERP — tal como no teu código
            links.append((href, data_text))
        except Exception:
            continue

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        save_html(driver, f"no_results_serp_{int(time.time())}.html")
    return links

# -------------------------------------------------------------
# Visitar links e voltar
# -------------------------------------------------------------
def visitar_links(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links...")
    results_url = driver.current_url
    for href_google, data_pub in links:
        try:
            # Clicar pelo href EXATO do SERP (com redirecionamento do Google)
            try:
                link_element = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[@href='{href_google}']"))
                )
            except Exception:
                # fallback: procurar por starts-with (casos com parâmetros dinâmicos de tracking)
                try:
                    link_element = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, f"//a[starts-with(@href, '{href_google.split('&')[0]}')]"))
                    )
                except Exception:
                    link_element = None

            if link_element is None:
                # fallback duro: abrir diretamente
                open_url_with_timeout(driver, href_google, soft_wait=0.8)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_element)
                time.sleep(0.4)
                if not try_click(driver, link_element, prefix="abrir_artigo"):
                    # se click falhar, abrir via location
                    driver.execute_script("window.location = arguments[0];", href_google)
                time.sleep(1.2)

            # Possíveis cookies do site
            try:
                aceitar_cookies_se_existem(driver, prefix="site_cookie")
            except Exception:
                pass

            # Recolher conteúdo
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
            resultados.append({
                "link": href_google,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": str(e)
            })
        finally:
            # Voltar tal como no teu fluxo, mas com salvaguarda
            try:
                driver.back()
                time.sleep(1.2)
            except Exception:
                try:
                    open_url_with_timeout(driver, results_url, soft_wait=0.6)
                except Exception:
                    pass

# -------------------------------------------------------------
# Próxima página (preferir click; fallback por parâmetro)
# -------------------------------------------------------------
def proxima_pagina(driver):
    log("[DEBUG] Próxima página...")
    try:
        nxt = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.ID, "pnnext")))
        if try_click(driver, nxt, prefix="pnnext"):
            time.sleep(1.0)
            return True
    except Exception:
        pass

    # Fallback por URL (parâmetro start)
    try:
        parsed = urlparse(driver.current_url)
        qs = dict([kv for kv in [p.split("=",1) if "=" in p else (p,"") for p in parsed.query.split("&") if p]])
        start = int(qs.get("start","0") or "0")
        qs["start"] = str(start + 10)
        new_query = "&".join([f"{k}={v}" for k,v in qs.items()])
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        prev = driver.current_url
        open_url_with_timeout(driver, new_url, soft_wait=0.8)
        if driver.current_url == prev:
            log("[DEBUG] URL não mudou ao paginar — a parar.")
            return False
        return True
    except Exception:
        return False

# -------------------------------------------------------------
# Execução principal (adaptação fiel à tua lógica)
# -------------------------------------------------------------
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
    options.add_argument("--lang=pt-PT")
    options.add_argument(f"--user-agent={USER_AGENT}")
    # Acelerar sem alterar a lógica:
    options.page_load_strategy = "eager"  # não espera todos os recursos
    options.add_argument("--disable-features=PaintHolding")
    options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2  # desliga imagens
    })

    # Se precisares alinhar com o teu local (137), descomenta:
    # driver = uc.Chrome(options=options, version_main=137)
    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(PAGELOAD_TIMEOUT)
    driver.set_script_timeout(SCRIPT_TIMEOUT)
    driver.set_window_size(1366, 768)

    resultados = []
    try:
        open_url_with_timeout(driver, "https://www.google.com/ncr", soft_wait=0.8)
        aceitar_cookies_se_existem(driver, prefix="google_cookies_ncr")

        abrir_pesquisa_google(driver, keyword)
        # clicar separador Notícias (fluxo original)
        if not clicar_noticias_tab(driver):
            log("[DEBUG] Tab Notícias não encontrada/clicável.")
            # Fallback leve (mantendo o resto do fluxo): forçar por URL e continuar
            ir_para_noticias_por_url(driver, keyword)

        aplicar_filtro_tempo(driver, filtro_tempo)
        # Reforço leve por URL se o menu falhar silenciosamente
        aplicar_filtro_tempo_por_url(driver, filtro_tempo)
        clicar_linguagem(driver)

        # Esperar que existam headings de notícias ou resultados
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='heading']"))
            )
        except Exception:
            pass

        # Loop de páginas
        while True:
            links = coletar_links_noticias(driver, excluir_br=False)
            if links:
                visitar_links(driver, links, keyword, resultados)
            if not proxima_pagina(driver):
                break
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
    log("Script iniciado.")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas', 'Última semana', 'Último mês', 'Último ano'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))