import os
import time
import re
from urllib.parse import urlparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    TimeoutException,
)

HEADLESS = False  # True para headless, False para ver o browser
SCREENSHOT_DIR = "fotos_erros"

def ensure_screenshot_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def save_shot(driver, name):
    ensure_screenshot_dir()
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        driver.save_screenshot(path)
    except Exception:
        pass
    print(f"[DEBUG] Screenshot guardada: {path}")

def try_click_strategies(driver, element, prefix="click"):
    """Tenta várias estratégias de click até uma funcionar.
    Lança exceção se nenhuma resultar."""
    ensure_screenshot_dir()
    ts = int(time.time())
    # 1) Scroll to element
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
        time.sleep(0.4)
    except Exception:
        pass

    # 2) ActionChains move + click
    try:
        ActionChains(driver).move_to_element(element).pause(0.1).click(element).perform()
        save_shot(driver, f"{prefix}_action_{ts}.png")
        print("[DEBUG] Click via ActionChains OK")
        return
    except Exception as e:
        print(f"[DEBUG] ActionChains click falhou: {e}")

    # 3) Selenium element.click()
    try:
        element.click()
        save_shot(driver, f"{prefix}_selenium_{ts}.png")
        print("[DEBUG] Click via element.click() OK")
        return
    except Exception as e:
        print(f"[DEBUG] element.click() falhou: {e}")

    # 4) JS click (arguments[0].click())
    try:
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_js_{ts}.png")
        print("[DEBUG] Click via JS arguments[0].click() OK")
        return
    except Exception as e:
        print(f"[DEBUG] JS click falhou: {e}")

    # 5) Click via elementFromPoint (clique pelo centro do elemento)
    try:
        js = """
        var el = arguments[0];
        var r = el.getBoundingClientRect();
        var x = Math.floor(r.left + r.width/2);
        var y = Math.floor(r.top + r.height/2);
        var target = document.elementFromPoint(x, y);
        if(target) { target.click(); return true; }
        return false;
        """
        success = driver.execute_script(js, element)
        save_shot(driver, f"{prefix}_frompoint_{ts}.png")
        if success:
            print("[DEBUG] Click via elementFromPoint OK")
            return
        else:
            print("[DEBUG] elementFromPoint não encontrou target clicável.")
    except Exception as e:
        print(f"[DEBUG] elementFromPoint click falhou: {e}")

    # 6) Click por className (segundo exemplo do blog)
    try:
        class_name = element.get_attribute("class")
        if class_name:
            first_class = class_name.split()[0]
            js = f"""
            var elems = document.getElementsByClassName('{first_class}');
            if(elems.length) elems[0].click();
            """
            driver.execute_script(js)
            save_shot(driver, f"{prefix}_classclick_{ts}.png")
            print("[DEBUG] Click via className JS OK")
            return
    except Exception as e:
        print(f"[DEBUG] Click por className falhou: {e}")

    # 7) Remover overlays comuns e tentar click novamente
    try:
        driver.execute_script("""
        var overlays = document.querySelectorAll('div[role=dialog], .modal, .overlay, .popup, [aria-hidden="true"]');
        overlays.forEach(function(o){ try{o.style.display='none'; o.remove();}catch(e){} });
        """)
        time.sleep(0.3)
        # tenta JS click depois de remover overlays
        try:
            driver.execute_script("arguments[0].click();", element)
            save_shot(driver, f"{prefix}_after_removeoverlays_{ts}.png")
            print("[DEBUG] Click via JS após remover overlays OK")
            return
        except Exception as e:
            print(f"[DEBUG] Click via JS após remover overlays falhou: {e}")
    except Exception as e:
        print(f"[DEBUG] Remover overlays falhou: {e}")

    # 8) Última tentativa: scroll por offsets e click via JS
    try:
        driver.execute_script("window.scrollBy(0, -100);")
        time.sleep(0.2)
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", element)
        save_shot(driver, f"{prefix}_last_hope_{ts}.png")
        print("[DEBUG] Click via JS após scroll extra OK")
        return
    except Exception as e:
        print(f"[DEBUG] Última tentativa de click falhou: {e}")

    raise Exception("Nenhuma estratégia de click funcionou para o elemento.")

def localizar_botao_por_textos(driver, textos):
    """Procura botões que contenham qualquer dos textos fornecidos.
    Retorna primeiro elemento encontrado ou None."""
    for texto in textos:
        # XPath que procura botão, input ou span com texto parcial (case-insensitive via translate)
        xpath_variants = [
            f"//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{texto.lower()}')]",
            f"//div[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{texto.lower()}')]",
            f"//span[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{texto.lower()}')]",
            f"//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{texto.lower()}')]",
            f"//input[@type='button' and contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{texto.lower()}')]",
        ]
        for xp in xpath_variants:
            try:
                elems = driver.find_elements(By.XPATH, xp)
                if elems:
                    # Escolhe o primeiro visível
                    for e in elems:
                        try:
                            if e.is_displayed():
                                return e
                        except Exception:
                            return elems[0]
            except Exception:
                continue
    return None

def aceitar_cookies_se_existem(driver, screenshot_prefix="cookies"):
    """Estratégia robusta para aceitar cookies (fora e dentro de iframes)."""
    ensure_screenshot_dir()
    print("[DEBUG] A tentar aceitar cookies (estratégia robusta)...")
    time.sleep(1.2)

    textos = ['Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Consent', 'Agree', 'OK', 'Aceitar cookies', 'Aceitar todos']
    # 1) Tenta fora de iframes
    try:
        btn = localizar_botao_por_textos(driver, textos)
        if btn:
            print("[DEBUG] Botão de cookies encontrado FORA de iframes.")
            save_shot(driver, f"{screenshot_prefix}_found_out_{int(time.time())}.png")
            try:
                try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_out")
                print("[DEBUG] Cookies aceites (fora iframe).")
                return True
            except Exception as e:
                print(f"[DEBUG] Tentativas de click fora iframe falharam: {e}")
    except Exception as e:
        print(f"[DEBUG] Erro a procurar fora iframe: {e}")

    # 2) Tenta dentro de iframes (esperar e iterar)
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"[DEBUG] {len(iframes)} iframes encontrados.")
        for idx, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                time.sleep(0.3)
                btn = localizar_botao_por_textos(driver, textos)
                if btn:
                    print(f"[DEBUG] Botão de cookies encontrado DENTRO do iframe {idx}.")
                    save_shot(driver, f"{screenshot_prefix}_found_in_{idx}_{int(time.time())}.png")
                    try:
                        try_click_strategies(driver, btn, prefix=f"{screenshot_prefix}_in_{idx}")
                        driver.switch_to.default_content()
                        print("[DEBUG] Cookies aceites (dentro iframe).")
                        return True
                    except Exception as e:
                        print(f"[DEBUG] Tentativas de click dentro do iframe {idx} falharam: {e}")
                driver.switch_to.default_content()
            except Exception as e:
                print(f"[DEBUG] Erro ao processar iframe {idx}: {e}")
                driver.switch_to.default_content()
    except Exception as e:
        print(f"[DEBUG] Erro ao enumerar iframes: {e}")
        driver.switch_to.default_content()

    # 3) Tenta comandos JS genéricos para clicar em elementos de consentimento conhecidos
    try:
        js_candidates = [
            "document.querySelector('button[aria-label=\"Accept all\"]')",
            "document.querySelector('button[aria-label*=\"accept\"])",
            "document.querySelector('[id*=\"consent\"] button')",
            "document.querySelector('[id*=\"cookie\"] button')",
            "document.querySelector('.qc-cmp2-summary-buttons .qc-cmp2-submit')",
            "document.querySelector('button[data-testid*=\"accept\"]')",
        ]
        for i, sel in enumerate(js_candidates):
            try:
                js_click = f"var el = {sel}; if(el){{ el.click(); return true; }} return false;"
                ok = driver.execute_script(js_click)
                save_shot(driver, f"{screenshot_prefix}_jscandidate_{i}_{int(time.time())}.png")
                if ok:
                    print("[DEBUG] Cookies aceites via JS generic.")
                    return True
            except Exception as e:
                print(f"[DEBUG] JS candidate {i} falhou: {e}")
    except Exception as e:
        print(f"[DEBUG] Erro nas tentativas JS genéricas: {e}")

    # 4) Tenta forçar clique no centro da janela (por exemplo quando há overlays deslocadas)
    try:
        js_force = """
        var buttons = Array.from(document.querySelectorAll('button, a, span, input[type=button]'));
        var texts = ['accept', 'aceitar', 'agree', 'concordo', 'ok'];
        for(var i=0;i<buttons.length;i++){
            var b = buttons[i];
            try{
                var txt = (b.innerText || b.value || '').toLowerCase();
                for(var j=0;j<texts.length;j++){
                    if(txt.indexOf(texts[j])!==-1){
                        b.click(); return true;
                    }
                }
            }catch(e){}
        }
        return false;
        """
        ok = driver.execute_script(js_force)
        save_shot(driver, f"{screenshot_prefix}_forcecenter_{int(time.time())}.png")
        if ok:
            print("[DEBUG] Cookies aceites via scan global JS.")
            return True
    except Exception as e:
        print(f"[DEBUG] Force scan JS falhou: {e}")

    # 5) Não encontrou: guarda screenshot e sai
    save_shot(driver, f"{screenshot_prefix}_nao_encontrado_{int(time.time())}.png")
    print("[DEBUG] Nenhum botão de cookies conseguido clicar.")
    return False

# As restantes funções do scraper (idênticas à estrutura que já tinhas):
def clicar_noticias_tab(driver):
    print("[DEBUG] A tentar clicar no separador Notícias...")
    try:
        noticias_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'tbm=nws')]"))
        )
        try:
            try_click_strategies(driver, noticias_tab, prefix="noticias_tab")
        except Exception:
            noticias_tab.click()
        time.sleep(2)
        return True
    except Exception as e:
        save_shot(driver, f"erro_noticias_tab_{int(time.time())}.png")
        print(f"[ERRO clicar_noticias_tab]: {e}")
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    print(f"[DEBUG] A tentar aplicar filtro de tempo: {filtro_tempo}")
    try:
        btn_ferramentas = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Ferramentas']"))
        )
        try:
            try_click_strategies(driver, btn_ferramentas, prefix="ferramentas")
        except Exception:
            btn_ferramentas.click()
        time.sleep(1.3)
        btn_recentes = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Recentes']"))
        )
        try:
            try_click_strategies(driver, btn_recentes, prefix="recentes")
        except Exception:
            btn_recentes.click()
        time.sleep(1.3)
        menu_itens = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']"))
        )
        for item in menu_itens:
            if filtro_tempo.strip().lower() in item.text.strip().lower():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.3)
                try:
                    try_click_strategies(driver, item, prefix="menu_itemradio")
                except Exception:
                    item.click()
                break
        time.sleep(1.5)
    except Exception as e:
        save_shot(driver, f"erro_filtro_tempo_{int(time.time())}.png")
        print(f"[ERRO filtro]: {e}")

def clicar_linguagem(driver):
    print("[DEBUG] A tentar clicar para filtrar por língua...")
    try:
        pesquisar_div = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'KTBKoe') and contains(text(), 'Pesquisar na Web')]"))
        )
        try:
            try_click_strategies(driver, pesquisar_div, prefix="pesquisar_linguagem")
        except Exception:
            pesquisar_div.click()
        time.sleep(1.0)
        link_pt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Pesquisar páginas em Português')]"))
        )
        try:
            try_click_strategies(driver, link_pt, prefix="pesquisar_pt")
        except Exception:
            link_pt.click()
        time.sleep(1.0)
    except Exception as e:
        save_shot(driver, f"erro_linguagem_{int(time.time())}.png")
        print(f"[ERRO clicar_linguagem]: {e}")

def coletar_links_noticias(driver):
    print("[DEBUG] A recolher links das notícias...")
    try:
        blocos = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[@role='heading' and contains(@class,'n0jPhd')]"))
        )
        links = []
        for bloco in blocos:
            try:
                a_element = bloco.find_element(By.XPATH, ".//ancestor::a[1]")
                href = a_element.get_attribute("href")
                if not href or not href.startswith("http"):
                    continue
                parsed = urlparse(href)
                domain = parsed.netloc.lower()
                if ".br" in domain:
                    continue
                # tenta extrair data
                data_text = "N/D"
                try:
                    data_parent = bloco.find_element(By.XPATH, "./../../..")
                    spans = data_parent.find_elements(By.XPATH, ".//span")
                    for span in spans:
                        texto = span.text.strip()
                        if re.search(r"\d", texto):
                            data_text = texto
                            break
                except Exception:
                    data_text = "N/D"
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
    print(f"[DEBUG] A visitar {len(links)} links de notícias...")
    for url, data_pub in links:
        try:
            link_element = driver.find_element(By.XPATH, f"//a[@href='{url}']")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
            time.sleep(0.7)
            try:
                try_click_strategies(driver, link_element, prefix="visitar_link")
            except Exception:
                link_element.click()
            time.sleep(3.5)
            # tenta aceitar cookies no site visitado
            try:
                aceitar_cookies_se_existem(driver, screenshot_prefix="site_cookie")
            except Exception:
                pass
            # recolhe texto
            corpo = ""
            try:
                artigos = driver.find_elements(By.TAG_NAME, "article")
                if artigos:
                    corpo = " ".join([a.text for a in artigos if a.text.strip()])
                else:
                    divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'content') or contains(@class, 'article')]")
                    corpo = " ".join([div.text for div in divs if div.text.strip()])
                if not corpo:
                    corpo = driver.page_source
            except Exception:
                corpo = driver.page_source
            titulo = driver.title or "Sem título"
            parsed = urlparse(url)
            site_name = parsed.netloc
            encontrou = keyword.lower() in corpo.lower()
            status = "ENCONTRADA" if encontrou else "NÃO ENCONTRADA"
            resultados.append({
                "link": url,
                "titulo": titulo,
                "site": site_name,
                "status": status,
                "data": data_pub
            })
            driver.back()
            time.sleep(2.0)
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
                time.sleep(1.5)
            except Exception:
                pass

def proxima_pagina(driver):
    print("[DEBUG] A tentar avançar para a próxima página de notícias...")
    try:
        next_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "pnnext"))
        )
        try:
            try_click_strategies(driver, next_btn, prefix="proxima_pagina")
        except Exception:
            next_btn.click()
        time.sleep(2.0)
        return True
    except Exception as e:
        save_shot(driver, f"erro_proxima_pagina_{int(time.time())}.png")
        print(f"[ERRO proxima_pagina]: {e}")
        return False

def executar_scraper_google(keyword, filtro_tempo):
    print("[DEBUG] A iniciar o scraper do Google...")
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1024")
    driver = uc.Chrome(options=options)
    driver.set_window_size(1280, 1024)
    resultados = []
    try:
        driver.get("https://www.google.com")
        # esperar um pouco para carregar consent etc
        time.sleep(1.2)
        aceitar_cookies_se_existem(driver, screenshot_prefix="google_cookies")
        # pesquisa
        search_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "q")))
        time.sleep(0.5)
        search_input.clear()
        search_input.send_keys(keyword)
        search_input.send_keys(Keys.ENTER)
        time.sleep(2.2)
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
            res = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(res)
        except Exception as e:
            print(f"[ERRO geral]: {e}")
            all_results.append({"keyword": kw, "erro": str(e)})
    return all_results

if __name__ == "__main__":
    print("[DEBUG] Script iniciado.")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    print(resultados)