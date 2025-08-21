import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urlunparse, urljoin, urlparse as _uparse, parse_qs, urlencode, urlunparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException
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

def open_url_with_timeout(driver, url, timeout=PAGELOAD_TIMEOUT, soft_wait=1.2):
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

def aceitar_cookies_se_existem(driver, prefix="cookies"):
    try:
        log("[DEBUG] A tentar aceitar cookies...")
        time.sleep(0.5)
        textos = ['Aceitar tudo','Accept all','Aceitar','Concordo','Consent','Agree','OK','Aceitar cookies','Aceitar todos']
        # Fora iframes
        for xp in [
            "//button//div[normalize-space(text())='Aceitar tudo']",
            "//button[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
            "//div[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
            "//span[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
            "//button[contains(@aria-label, 'Accept')]",
        ]:
            try:
                btn = driver.find_element(By.XPATH, xp)
                if btn and try_click(driver, btn, prefix=f"{prefix}_out"):
                    log("[DEBUG] Cookies aceites (fora iframe).")
                    return True
            except Exception:
                pass

        # iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for i, fr in enumerate(iframes):
            try:
                driver.switch_to.frame(fr)
                time.sleep(0.2)
                for xp in [
                    "//button//div[normalize-space(text())='Aceitar tudo']",
                    "//button[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
                    "//div[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
                    "//span[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
                    "//button[contains(@aria-label, 'Accept')]",
                ]:
                    try:
                        btn = driver.find_element(By.XPATH, xp)
                        if btn and try_click(driver, btn, prefix=f"{prefix}_in_{i}"):
                            driver.switch_to.default_content()
                            log("[DEBUG] Cookies aceites (iframe).")
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

def abrir_pesquisa_google(driver, keyword):
    url = f"https://www.google.com/search?q={keyword}&hl=pt-PT&gl=pt"
    open_url_with_timeout(driver, url, soft_wait=1.0)
    aceitar_cookies_se_existem(driver, prefix="google_cookies_search")

def clicar_noticias_tab(driver):
    log("[DEBUG] A clicar no separador Notícias...")
    try:
        el = WebDriverWait(driver, 12).until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'tbm=nws')]")))
        if try_click(driver, el, prefix="tab_noticias"):
            time.sleep(1.2)
            return True
    except Exception as e:
        log(f"[ERRO clicar_noticias_tab]: {e}")
    return False

def forcar_udm14(driver):
    # Simplifica o markup do SERP (mais fácil apanhar h3/a)
    try:
        cur = driver.current_url
        p = _uparse(cur)
        qs = parse_qs(p.query)
        if qs.get("udm", [""])[0] != "14":
            qs["udm"] = ["14"]
            newq = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
            new_url = urlunparse((p.scheme, p.netloc, p.path, p.params, newq, p.fragment))
            open_url_with_timeout(driver, new_url, soft_wait=1.0)
            aceitar_cookies_se_existem(driver, prefix="google_cookies_udm")
            log("[DEBUG] UDM=14 aplicado.")
    except Exception as e:
        log(f"[DEBUG] Falha a aplicar UDM=14: {e}")

def aplicar_filtro_tempo(driver, filtro_tempo):
    if not filtro_tempo or not filtro_tempo.strip():
        return
    log(f"[DEBUG] A aplicar filtro de tempo: {filtro_tempo}")
    try:
        btn_ferr = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']")))
        try_click(driver, btn_ferr, prefix="ferramentas")
        time.sleep(0.8)

        btn_recent = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']")))
        try_click(driver, btn_recent, prefix="recentes")
        time.sleep(0.8)

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
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", alvo)
            time.sleep(1.0)
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

def contar_seletores(driver):
    sels = {
        "div.dbsr a": "//div[contains(@class,'dbsr')]//a[@href]",
        "a.WlydOe": "//a[contains(@class,'WlydOe')][@href]",
        "a.tHmfQe": "//a[contains(@class,'tHmfQe')][@href]",
        "a.VDXfz": "//a[contains(@class,'VDXfz')][@href]",
        "a with h3": "//a[.//h3][@href]",
        "a with role=heading": "//a[.//div[@role='heading']][@href]",
        "heading n0jPhd": "//div[@role='heading' and contains(@class,'n0jPhd')]",
        "all anchors": "//a[@href]"
    }
    counts = {}
    for name, xp in sels.items():
        try:
            counts[name] = len(driver.find_elements(By.XPATH, xp))
        except Exception:
            counts[name] = -1
    log(f"[DEBUG] Contagens seletores: {counts}")

def coletar_links_noticias(driver, excluir_br=False):
    log("[DEBUG] A recolher links das notícias...")
    links = []
    seen = set()

    # 3 tentativas com scroll (conteúdo lazy)
    for attempt in range(3):
        if attempt > 0:
            try:
                driver.execute_script("window.scrollBy(0, Math.max(900, window.innerHeight*0.9));")
            except Exception:
                pass
            time.sleep(0.9)

        # Estratégias de anchors (prioridade)
        strategies = [
            ("dbsr", "//div[contains(@class,'dbsr')]//a[@href]"),
            ("WlydOe", "//a[contains(@class,'WlydOe')][@href]"),
            ("tHmfQe", "//a[contains(@class,'tHmfQe')][@href]"),
            ("VDXfz", "//a[contains(@class,'VDXfz')][@href]"),
            ("a_h3", "//a[.//h3][@href]"),
            ("a_role_heading", "//a[.//div[@role='heading']][@href]"),
        ]

        found_any = False
        for name, xp in strategies:
            try:
                anchors = driver.find_elements(By.XPATH, xp)
            except Exception:
                anchors = []
            if not anchors:
                continue

            for a_el in anchors:
                try:
                    href = a_el.get_attribute("href") or ""
                    if not href:
                        continue
                    if not (href.startswith("http") or href.startswith("/url")):
                        continue

                    # data (procurar próximo do container)
                    data_text = "N/D"
                    try:
                        container = a_el.find_element(By.XPATH, "./ancestor::*[self::div or self::article][1]")
                    except Exception:
                        container = a_el
                    try:
                        spans = container.find_elements(By.XPATH, ".//span|.//time")
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

                    key = href
                    if key in seen:
                        continue
                    # filtro .br opcional (só se href for http)
                    try:
                        if excluir_br and href.startswith("http"):
                            dom = urlparse(href).netloc.lower()
                            if dom.endswith(".br"):
                                continue
                    except Exception:
                        pass

                    seen.add(key)
                    links.append((href, data_text))
                except Exception:
                    continue

            if links:
                found_any = True
                break

        # Último recurso: o teu caminho original (heading -> ancestor::a)
        if not found_any:
            try:
                blocos = driver.find_elements(By.XPATH, "//div[@role='heading' and contains(@class,'n0jPhd')]")
            except Exception:
                blocos = []
            for bloco in blocos:
                try:
                    a_el = bloco.find_element(By.XPATH, ".//ancestor::a[1]")
                    href = a_el.get_attribute("href") or ""
                    if not href:
                        continue
                    if not (href.startswith("http") or href.startswith("/url")):
                        continue
                    data_text = "N/D"
                    try:
                        data_parent = bloco.find_element(By.XPATH, "./../../..")
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
                    key = href
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append((href, data_text))
                except Exception:
                    continue

        if links:
            break

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        contar_seletores(driver)
        save_shot(driver, f"no_results_serp_{int(time.time())}.png")
        save_html(driver, f"no_results_serp_{int(time.time())}.html")
    return links

def resolve_visit_href(href):
    try:
        if href.startswith("/"):
            return urljoin("https://www.google.com", href)
        return href
    except Exception:
        return href

def visitar_links(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links...")
    results_url = driver.current_url
    for href_google, data_pub in links:
        try:
            # Tentar clicar o mesmo <a> do SERP
            try:
                link_element = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[@href='{href_google}']"))
                )
            except Exception:
                # fallback: starts-with
                try:
                    base = href_google.split("&")[0].replace("'", "\\'")
                    link_element = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, f"//a[starts-with(@href, '{base}')]"))
                    )
                except Exception:
                    link_element = None

            if link_element is None:
                # abrir diretamente (resolve /url relativo)
                open_url_with_timeout(driver, resolve_visit_href(href_google), soft_wait=1.2)
            else:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_element)
                time.sleep(0.4)
                if not try_click(driver, link_element, prefix="abrir_artigo"):
                    driver.execute_script("window.location = arguments[0];", resolve_visit_href(href_google))
                time.sleep(1.6)

            # Cookies do site
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
            # Voltar à SERP
            try:
                driver.back()
                time.sleep(1.2)
            except Exception:
                try:
                    open_url_with_timeout(driver, results_url, soft_wait=0.8)
                except Exception:
                    pass

def proxima_pagina(driver):
    log("[DEBUG] Próxima página...")
    try:
        nxt = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.ID, "pnnext")))
        if try_click(driver, nxt, prefix="pnnext"):
            time.sleep(1.2)
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
        open_url_with_timeout(driver, new_url, soft_wait=1.0)
        return True
    except Exception:
        return False

def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (fluxo original com coleta robusta).")
    options = uc.ChromeOptions()
    # Dica: para testar visualmente, comenta a linha headless abaixo
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

        abrir_pesquisa_google(driver, keyword)
        if not clicar_noticias_tab(driver):
            log("[DEBUG] Tab Notícias não encontrada/clicável.")
            save_shot(driver, f"no_news_tab_{int(time.time())}.png")
            save_html(driver, f"no_news_tab_{int(time.time())}.html")
            return resultados

        # Simplificar markup
        forcar_udm14(driver)

        aplicar_filtro_tempo(driver, filtro_tempo)
        clicar_linguagem(driver)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[@href and (starts-with(@href,'/url') or starts-with(@href,'http'))]"))
            )
        except Exception:
            pass

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