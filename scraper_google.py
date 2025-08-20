import os
import time
import re
from datetime import datetime
from urllib.parse import urlparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    WebDriverException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    NoSuchElementException,
    TimeoutException,
)

# Configurações
HEADLESS = True                      # Executa invisível
USE_LANGUAGE_FILTER = False          # Define True se quiseres aplicar o filtro de língua
SCREENSHOT_DIR = "fotos_erros"
LOG_FILE = os.path.join(SCREENSHOT_DIR, "scraper.log")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
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

def page_debug_info(driver):
    try:
        url = driver.current_url
    except Exception:
        url = "N/A"
    try:
        state = driver.execute_script("return document.readyState")
    except Exception:
        state = "N/A"
    try:
        iframes = len(driver.find_elements(By.TAG_NAME, "iframe"))
    except Exception:
        iframes = -1
    return f"url={url} readyState={state} iframes={iframes}"

def log_exception(e, context, driver, shot_prefix="erro"):
    etype = type(e).__name__
    msg = getattr(e, "msg", None) or str(e)
    stack = getattr(e, "stacktrace", None)
    log(f"[ERRO][{context}] {etype}: {msg}")
    if stack:
        log(f"[STACKTRACE][{context}]\n{stack}")
    log(f"[PAGE][{context}] {page_debug_info(driver)}")
    save_shot(driver, f"{shot_prefix}_{context}_{int(time.time())}.png")

def wait_ready(driver, timeout=15):
    WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") == "complete")

# -----------------------------------------------------------------------------
# Cliques robustos
# -----------------------------------------------------------------------------
def try_click_strategies(driver, element, prefix="click"):
    """Tentativas de click resilientes contra intercepts/not interactable/overlays."""
    ts = int(time.time())

    # Garantir visibilidade/viewport
    try:
        WebDriverWait(driver, 6).until(EC.visibility_of(element))
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
        time.sleep(0.2)
    except Exception:
        pass

    # ActionChains
    try:
        ActionChains(driver).move_to_element(element).pause(0.05).click(element).perform()
        save_shot(driver, f"{prefix}_action_{ts}.png")
        log("[DEBUG] Click via ActionChains OK")
        return
    except Exception as e:
        log(f"[DEBUG] ActionChains falhou: {e}")

    # element.click()
    try:
        element.click()
        save_shot(driver, f"{prefix}_selenium_{ts}.png")
        log("[DEBUG] Click via element.click() OK")
        return
    except Exception as e:
        log(f"[DEBUG] element.click() falhou: {e}")

    # JS click
    try:
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_js_{ts}.png")
        log("[DEBUG] Click via JS arguments[0].click() OK")
        return
    except Exception as e:
        log(f"[DEBUG] JS click falhou: {e}")

    # elementFromPoint
    try:
        success = driver.execute_script("""
            var el = arguments[0];
            if (!el) return false;
            var r = el.getBoundingClientRect();
            var x = Math.floor(r.left + r.width/2);
            var y = Math.floor(r.top + r.height/2);
            var target = document.elementFromPoint(x, y);
            if (target) { target.click(); return true; }
            return false;
        """, element)
        save_shot(driver, f"{prefix}_frompoint_{ts}.png")
        if success:
            log("[DEBUG] Click via elementFromPoint OK")
            return
    except Exception as e:
        log(f"[DEBUG] elementFromPoint falhou: {e}")

    # Remover overlays e tentar JS click
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
        log("[DEBUG] Click via JS após remover overlays OK")
        return
    except Exception as e:
        log(f"[DEBUG] Após remover overlays falhou: {e}")

    # Última tentativa: scroll, JS click
    try:
        driver.execute_script("window.scrollBy(0, -120);")
        time.sleep(0.2)
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.2)
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_last_hope_{ts}.png")
        log("[DEBUG] Click via JS após scroll extra OK")
        return
    except Exception as e:
        log(f"[DEBUG] Última tentativa falhou: {e}")

    raise ElementNotInteractableException("Nenhuma estratégia de click funcionou para o elemento.")

# -----------------------------------------------------------------------------
# Cookies / iframes
# -----------------------------------------------------------------------------
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
        log("[DEBUG] A tentar aceitar cookies (estratégia robusta)...")
        time.sleep(0.8)
        textos = ['Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Consent', 'Agree', 'OK', 'Aceitar cookies', 'Aceitar todos']

        # Fora de iframes
        btn = localizar_botao_por_textos(driver, textos)
        if btn:
            log("[DEBUG] Botão de cookies encontrado FORA de iframes.")
            save_shot(driver, f"{screenshot_prefix}_found_out_{int(time.time())}.png")
            try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_out")
            log("[DEBUG] Cookies aceites (fora iframe).")
            # Fechar possíveis popups residuais por segurança
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.2)
            except Exception:
                pass
            return True

        # Dentro de iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log(f"[DEBUG] {len(iframes)} iframes encontrados.")
        for idx, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                time.sleep(0.2)
                btn = localizar_botao_por_textos(driver, textos)
                if btn:
                    log(f"[DEBUG] Botão de cookies encontrado DENTRO do iframe {idx}.")
                    save_shot(driver, f"{screenshot_prefix}_found_in_{idx}_{int(time.time())}.png")
                    try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_in_{idx}")
                    driver.switch_to.default_content()
                    log("[DEBUG] Cookies aceites (dentro iframe).")
                    try:
                        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                        time.sleep(0.2)
                    except Exception:
                        pass
                    return True
                driver.switch_to.default_content()
            except Exception as e:
                driver.switch_to.default_content()
                log(f"[DEBUG] Erro ao processar iframe {idx}: {e}")

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
                save_shot(driver, f"{screenshot_prefix}_jscand_{i}_{int(time.time())}.png")
                log("[DEBUG] Cookies aceites via JS generic.")
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                    time.sleep(0.2)
                except Exception:
                    pass
                return True

        save_shot(driver, f"{screenshot_prefix}_nao_encontrado_{int(time.time())}.png")
        log("[DEBUG] Nenhum botão de cookies encontrado/clicado.")
        return False
    except Exception as e:
        log_exception(e, "aceitar_cookies", driver, "cookies_erro")
        return False

# -----------------------------------------------------------------------------
# Pesquisa Google
# -----------------------------------------------------------------------------
def obter_campo_pesquisa(driver):
    wait = WebDriverWait(driver, 15)
    candidatos = [
        (By.CSS_SELECTOR, "textarea[name='q']"),
        (By.CSS_SELECTOR, "input[name='q']"),
    ]
    ultimo_erro = None
    for by, sel in candidatos:
        try:
            elem = wait.until(EC.visibility_of_element_located((by, sel)))
            elem = wait.until(EC.element_to_be_clickable((by, sel)))
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
                time.sleep(0.1)
            except Exception:
                pass
            return elem
        except Exception as e:
            ultimo_erro = e
            continue
    raise ElementNotInteractableException(f"Campo de pesquisa não interactivo: {ultimo_erro}")

def escrever_e_pesquisar(driver, keyword):
    caixa = obter_campo_pesquisa(driver)

    # Focar
    try:
        try_click_strategies(driver, caixa, prefix="focus_search")
    except Exception:
        try:
            caixa.click()
        except Exception:
            pass

    # Limpar
    try:
        caixa.clear()
    except Exception:
        pass
    try:
        caixa.send_keys(Keys.CONTROL, "a")
        caixa.send_keys(Keys.BACK_SPACE)
    except Exception:
        try:
            driver.execute_script("arguments[0].value='';", caixa)
        except Exception:
            pass

    # Escrever + Enter
    try:
        caixa.send_keys(keyword)
        time.sleep(0.1)
        caixa.send_keys(Keys.ENTER)
        return
    except Exception:
        # Fallback JS + Enter no body
        try:
            driver.execute_script("""
                var el = arguments[0], val = arguments[1];
                if (!el) return;
                el.value = val;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            """, caixa, keyword)
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ENTER)
            return
        except Exception as e:
            raise ElementNotInteractableException(f"Falha a pesquisar via JS: {e}")

def clicar_noticias_tab(driver):
    log("[DEBUG] A tentar clicar no separador Notícias...")
    try:
        wait = WebDriverWait(driver, 12)
        candidatos = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@href,'tbm=nws')]")))
        tab = None
        for el in candidatos:
            try:
                if el.is_displayed() and el.is_enabled():
                    tab = el
                    break
            except Exception:
                continue
        if not tab:
            raise TimeoutException("Tab Notícias não interactiva")
        try_click_strategies(driver, tab, prefix="noticias_tab")
        time.sleep(0.4)
        return True
    except Exception as e:
        log_exception(e, "clicar_noticias_tab", driver, "noticias_tab")
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    log(f"[DEBUG] A aplicar filtro de tempo: {filtro_tempo}")
    try:
        wait = WebDriverWait(driver, 12)
        btn_ferramentas = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']")))
        try_click_strategies(driver, btn_ferramentas, prefix="ferramentas")
        time.sleep(0.5)

        btn_recentes = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']")))
        try_click_strategies(driver, btn_recentes, prefix="recentes")
        time.sleep(0.4)

        menu_itens = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']")))
        alvo = None
        for item in menu_itens:
            if filtro_tempo.strip().lower() in item.text.strip().lower():
                alvo = item
                break
        if alvo:
            try_click_strategies(driver, alvo, prefix="menu_itemradio")
            time.sleep(0.4)
    except Exception as e:
        log_exception(e, "aplicar_filtro_tempo", driver, "filtro_tempo")

def clicar_linguagem(driver):
    if not USE_LANGUAGE_FILTER:
        return
    log("[DEBUG] A definir filtro de língua...")
    try:
        wait = WebDriverWait(driver, 12)
        pesquisar_div = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'KTBKoe') and contains(.,'Pesquisar na Web')]")))
        try_click_strategies(driver, pesquisar_div, prefix="pesquisar_linguagem")
        time.sleep(0.4)

        link_pt = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Pesquisar páginas em Português')]")))
        try_click_strategies(driver, link_pt, prefix="pesquisar_pt")
        time.sleep(0.4)
    except Exception as e:
        log_exception(e, "clicar_linguagem", driver, "lingua")

# -----------------------------------------------------------------------------
# Notícias
# -----------------------------------------------------------------------------
def coletar_links_noticias(driver):
    log("[DEBUG] A recolher links das notícias...")
    try:
        wait = WebDriverWait(driver, 12)
        blocos = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//div[@role='heading' and contains(@class,'n0jPhd')]")))
        links = []
        for bloco in blocos:
            try:
                a_element = bloco.find_element(By.XPATH, ".//ancestor::a[1]")
                href = a_element.get_attribute("href")
                if not href or not href.startswith("http"):
                    continue
                domain = urlparse(href).netloc.lower()
                if ".br" in domain:
                    continue
                data_text = "N/D"
                try:
                    data_parent = bloco.find_element(By.XPATH, "./../../..")
                    spans = data_parent.find_elements(By.XPATH, ".//span")
                    for span in spans:
                        t = span.text.strip()
                        if re.search(r"\d", t):
                            data_text = t
                            break
                except Exception:
                    pass
                links.append((href, data_text))
            except Exception:
                continue
        log(f"[DEBUG] {len(links)} links recolhidos.")
        return links
    except Exception as e:
        log_exception(e, "coletar_links_noticias", driver, "coletar")
        return []

def visitar_links(driver, links, keyword, resultados):
    log(f"[DEBUG] A visitar {len(links)} links...")
    for url, data_pub in links:
        try:
            link_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f"//a[@href='{url}']"))
            )
            try_click_strategies(driver, link_element, prefix="visitar_link")
            time.sleep(1.6)

            # Cookies no site
            try:
                aceitar_cookies_se_existem(driver, screenshot_prefix="site_cookie")
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
            site_name = urlparse(url).netloc
            encontrou = keyword.lower() in corpo.lower()
            resultados.append({
                "link": url,
                "titulo": titulo,
                "site": site_name,
                "status": "ENCONTRADA" if encontrou else "NÃO ENCONTRADA",
                "data": data_pub
            })

            driver.back()
            wait_ready(driver, 10)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "search")))
            time.sleep(0.3)
        except Exception as e:
            log_exception(e, "visitar_links", driver, "visitar")
            resultados.append({
                "link": url,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": f"{type(e).__name__}: {str(e)}"
            })
            try:
                driver.back()
                wait_ready(driver, 10)
            except Exception:
                pass

def proxima_pagina(driver):
    log("[DEBUG] Próxima página de notícias...")
    try:
        next_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "pnnext")))
        try_click_strategies(driver, next_btn, prefix="proxima_pagina")
        time.sleep(0.8)
        return True
    except Exception as e:
        log_exception(e, "proxima_pagina", driver, "proxima")
        return False

# -----------------------------------------------------------------------------
# Execução
# -----------------------------------------------------------------------------
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar o scraper do Google (headless).")
    options = uc.ChromeOptions()
    # Headless e ajustes
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1024")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=2")
    options.add_argument("--disable-extensions")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = uc.Chrome(options=options)
    driver.set_window_size(1280, 1024)

    resultados = []
    try:
        driver.get("https://www.google.com")
        wait_ready(driver, 15)
        time.sleep(0.5)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies")

        escrever_e_pesquisar(driver, keyword)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "search")))
        time.sleep(0.3)

        if clicar_noticias_tab(driver):
            aplicar_filtro_tempo(driver, filtro_tempo)
            clicar_linguagem(driver)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//div[@role='heading']")))
            while True:
                links = coletar_links_noticias(driver)
                if links:
                    visitar_links(driver, links, keyword, resultados)
                if not proxima_pagina(driver):
                    break
    except Exception as e:
        log_exception(e, "executar_scraper_google", driver, "exec")
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
        try:
            log(f"[DEBUG] A processar keyword: '{kw}'")
            res = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(res)
        except Exception as e:
            log(f"[ERRO ao processar '{kw}']: {type(e).__name__}: {str(e)}")
            all_results.append({"keyword": kw, "erro": f"{type(e).__name__}: {str(e)}"})
    return all_results

if __name__ == "__main__":
    ensure_dirs()
    log("Script iniciado (headless).")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    log(str(resultados))