import os
import time
import re
from urllib.parse import urlparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    TimeoutException,
)

# Executar SEM mostrar o browser (headless)
HEADLESS = True
SCREENSHOT_DIR = "fotos_erros"

def ensure_screenshot_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def save_shot(driver, name):
    ensure_screenshot_dir()
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        driver.save_screenshot(path)
        print(f"[DEBUG] Screenshot guardada: {path}")
    except Exception:
        pass

def try_click_strategies(driver, element, prefix="click"):
    """Tenta várias estratégias de click até uma funcionar, mitigando 'element not interactable'."""
    ts = int(time.time())

    # 1) Espera visibilidade e 'clickable'
    try:
        WebDriverWait(driver, 6).until(EC.visibility_of(element))
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
        time.sleep(0.2)
    except Exception:
        pass

    # 2) ActionChains (move + click)
    try:
        ActionChains(driver).move_to_element(element).pause(0.05).click(element).perform()
        save_shot(driver, f"{prefix}_action_{ts}.png")
        return
    except Exception as e:
        print(f"[DEBUG] ActionChains falhou: {e}")

    # 3) click normal
    try:
        element.click()
        save_shot(driver, f"{prefix}_selenium_{ts}.png")
        return
    except Exception as e:
        print(f"[DEBUG] element.click() falhou: {e}")

    # 4) JS click
    try:
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_js_{ts}.png")
        return
    except Exception as e:
        print(f"[DEBUG] JS click falhou: {e}")

    # 5) elementFromPoint no centro do elemento
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
            return
    except Exception as e:
        print(f"[DEBUG] elementFromPoint falhou: {e}")

    # 6) Remover overlays comuns e tentar novamente
    try:
        driver.execute_script("""
            var overlays = document.querySelectorAll('div[role=dialog], .modal, .overlay, .popup, [aria-hidden="true"]');
            overlays.forEach(function(o){ try{ o.style.display='none'; o.remove(); }catch(e){} });
        """)
        time.sleep(0.2)
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_after_overlays_{ts}.png")
        return
    except Exception as e:
        print(f"[DEBUG] Após remover overlays falhou: {e}")

    raise ElementNotInteractableException("Nenhuma estratégia de click funcionou (element not interactable).")

def localizar_botao_por_textos(driver, textos):
    """Procura um botão/link/elemento clicável que contenha algum dos textos (case-insensitive)."""
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
    """Aceita cookies fora e dentro de iframes, mitigando overlays/iframes."""
    print("[DEBUG] A tentar aceitar cookies...")
    time.sleep(0.8)
    textos = ['Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Consent', 'Agree', 'OK', 'Aceitar cookies', 'Aceitar todos']

    # Fora de iframes
    btn = localizar_botao_por_textos(driver, textos)
    if btn:
        try:
            try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_out")
            print("[DEBUG] Cookies aceites (fora iframe).")
            return True
        except Exception as e:
            print(f"[DEBUG] Falhou aceitar fora iframe: {e}")

    # Dentro de iframes
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"[DEBUG] Iframes encontrados: {len(iframes)}")
    for idx, iframe in enumerate(iframes):
        try:
            driver.switch_to.frame(iframe)
            time.sleep(0.2)
            btn = localizar_botao_por_textos(driver, textos)
            if btn:
                try:
                    try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_in_{idx}")
                    driver.switch_to.default_content()
                    print("[DEBUG] Cookies aceites (dentro iframe).")
                    return True
                except Exception as e:
                    print(f"[DEBUG] Falhou aceitar no iframe {idx}: {e}")
            driver.switch_to.default_content()
        except Exception as e:
            print(f"[DEBUG] Erro a processar iframe {idx}: {e}")
            driver.switch_to.default_content()

    # Tentativa JS genérica
    js_candidates = [
        "document.querySelector('button[aria-label=\"Accept all\"]')",
        "document.querySelector('button[aria-label*=\"accept\" i]')",
        "document.querySelector('[id*=\"consent\" i] button')",
        "document.querySelector('[id*=\"cookie\" i] button')",
        "document.querySelector('.qc-cmp2-summary-buttons .qc-cmp2-submit')",
        "document.querySelector('button[data-testid*=\"accept\" i]')",
    ]
    for i, sel in enumerate(js_candidates):
        try:
            ok = driver.execute_script(f"var el = {sel}; if(el){{ el.click(); return true; }} return false;")
            if ok:
                save_shot(driver, f"{screenshot_prefix}_jscand_{i}_{int(time.time())}.png")
                print("[DEBUG] Cookies aceites via JS genérico.")
                return True
        except Exception:
            continue

    save_shot(driver, f"{screenshot_prefix}_nao_encontrado_{int(time.time())}.png")
    print("[DEBUG] Nenhum botão de cookies encontrado/clicado.")
    return False

def obter_campo_pesquisa(driver):
    """Obtém o campo de pesquisa do Google de forma robusta (textarea ou input), garantindo que está interactivo."""
    wait = WebDriverWait(driver, 12)
    candidatos = [
        (By.CSS_SELECTOR, "textarea[name='q']"),
        (By.CSS_SELECTOR, "input[name='q']"),
    ]
    ultimo_erro = None
    for by, sel in candidatos:
        try:
            elem = wait.until(EC.visibility_of_element_located((by, sel)))
            # Em alguns layouts, 'element_to_be_clickable' é necessário:
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
    """Foca o campo, apaga conteúdo e pesquisa. Mitiga 'element not interactable' com várias abordagens."""
    caixa = obter_campo_pesquisa(driver)

    # Tentar focar com estratégias
    try:
        try_click_strategies(driver, caixa, prefix="focus_search")
    except Exception:
        try:
            caixa.click()
        except Exception:
            pass

    # Limpar conteúdo de forma robusta
    try:
        caixa.clear()
    except Exception:
        pass

    try:
        caixa.send_keys(Keys.CONTROL, "a")
        caixa.send_keys(Keys.BACK_SPACE)
    except Exception:
        # Fallback JS para limpar
        try:
            driver.execute_script("arguments[0].value='';", caixa)
        except Exception:
            pass

    # Escrever termo
    try:
        caixa.send_keys(keyword)
        time.sleep(0.1)
        caixa.send_keys(Keys.ENTER)
        return
    except ElementNotInteractableException as e:
        print(f"[DEBUG] send_keys não interactivo: {e}")

    # Fallback JS: set value + disparar eventos + Enter na body
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
        raise ElementNotInteractableException(f"Falha a definir valor por JS: {e}")

def clicar_noticias_tab(driver):
    print("[DEBUG] A tentar clicar no separador Notícias...")
    try:
        wait = WebDriverWait(driver, 10)
        # Alguns layouts criam múltiplos elementos; escolhe visível
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
        time.sleep(0.6)
        return True
    except Exception as e:
        save_shot(driver, f"erro_noticias_tab_{int(time.time())}.png")
        print(f"[ERRO clicar_noticias_tab]: {e}")
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    print(f"[DEBUG] A aplicar filtro de tempo: {filtro_tempo}")
    try:
        wait = WebDriverWait(driver, 10)
        btn_ferramentas = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']")))
        try_click_strategies(driver, btn_ferramentas, prefix="ferramentas")
        time.sleep(0.6)

        btn_recentes = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']")))
        try_click_strategies(driver, btn_recentes, prefix="recentes")
        time.sleep(0.6)

        menu_itens = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']")))
        alvo = None
        for item in menu_itens:
            if filtro_tempo.strip().lower() in item.text.strip().lower():
                alvo = item
                break
        if alvo:
            try_click_strategies(driver, alvo, prefix="menu_itemradio")
            time.sleep(0.5)
    except Exception as e:
        save_shot(driver, f"erro_filtro_tempo_{int(time.time())}.png")
        print(f"[ERRO filtro]: {e}")

def clicar_linguagem(driver):
    print("[DEBUG] A definir filtro de língua...")
    try:
        wait = WebDriverWait(driver, 10)
        pesquisar_div = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'KTBKoe') and contains(.,'Pesquisar na Web')]")))
        try_click_strategies(driver, pesquisar_div, prefix="pesquisar_linguagem")
        time.sleep(0.5)

        link_pt = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Pesquisar páginas em Português')]")))
        try_click_strategies(driver, link_pt, prefix="pesquisar_pt")
        time.sleep(0.4)
    except Exception as e:
        save_shot(driver, f"erro_linguagem_{int(time.time())}.png")
        print(f"[ERRO clicar_linguagem]: {e}")

def coletar_links_noticias(driver):
    print("[DEBUG] A recolher links das notícias...")
    try:
        wait = WebDriverWait(driver, 10)
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
        print(f"[DEBUG] {len(links)} links recolhidos.")
        return links
    except Exception as e:
        save_shot(driver, f"erro_coletar_links_{int(time.time())}.png")
        print(f"[ERRO coletar_links_noticias]: {e}")
        return []

def visitar_links(driver, links, keyword, resultados):
    print(f"[DEBUG] A visitar {len(links)} links...")
    for url, data_pub in links:
        try:
            link_element = driver.find_element(By.XPATH, f"//a[@href='{url}']")
            try_click_strategies(driver, link_element, prefix="visitar_link")
            time.sleep(2.2)

            # Aceitar cookies no site aberto (se aparecer)
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
            time.sleep(1.6)
        except Exception as e:
            save_shot(driver, f"erro_visitar_link_{int(time.time())}.png")
            print(f"[ERRO visitar_links]: {e}")
            resultados.append({
                "link": url,
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": data_pub,
                "erro": str(e)
            })
            try:
                driver.back()
                time.sleep(1.2)
            except Exception:
                pass

def proxima_pagina(driver):
    print("[DEBUG] Próxima página de notícias...")
    try:
        next_btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.ID, "pnnext")))
        try_click_strategies(driver, next_btn, prefix="proxima_pagina")
        time.sleep(1.2)
        return True
    except Exception as e:
        save_shot(driver, f"erro_proxima_pagina_{int(time.time())}.png")
        print(f"[ERRO proxima_pagina]: {e}")
        return False

def executar_scraper_google(keyword, filtro_tempo):
    print("[DEBUG] A iniciar o scraper do Google (headless)...")
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")
    # ATENÇÃO: definir headless apenas via add_argument (nunca options.headless = ...)
    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")

    driver = uc.Chrome(options=options)
    driver.set_window_size(1280, 1024)

    resultados = []
    try:
        driver.get("https://www.google.com")
        WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
        time.sleep(0.8)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies")

        escrever_e_pesquisar(driver, keyword)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "search")))
        time.sleep(0.6)

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
    finally:
        driver.quit()
    return resultados

def rodar_scraper_sequencial(keywords_string, filtro_tempo):
    all_results = []
    keywords = [kw.strip() for kw in keywords_string.split(",") if kw.strip()]
    for kw in keywords:
        try:
            print(f"[DEBUG] A processar keyword: {kw}")
            res = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(res)
        except Exception as e:
            print(f"[ERRO ao processar keyword '{kw}']: {e}")
            all_results.append({"keyword": kw, "erro": str(e)})
    return all_results

if __name__ == "__main__":
    print("[DEBUG] Script iniciado (headless).")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    print(resultados)