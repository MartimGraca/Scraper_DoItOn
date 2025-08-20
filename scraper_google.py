import os
import time
import re
from urllib.parse import urlparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def safe_click(driver, element, screenshot_prefix="erro_click"):
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.5)
        screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_antes.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[DEBUG] Screenshot ANTES do click: {screenshot_nome}")
        if element.is_displayed() and element.is_enabled():
            try:
                element.click()
                print("[DEBUG] Click normal OK")
                screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_depois.png"
                driver.save_screenshot(screenshot_nome)
                print(f"[DEBUG] Screenshot DEPOIS do click: {screenshot_nome}")
                return
            except Exception as e:
                print(f"[DEBUG] Falhou click normal: {e}")
        else:
            print("[DEBUG] Elemento não está visível ou não está enabled.")

        # Tenta clicar com JS
        try:
            driver.execute_script("arguments[0].click();", element)
            print("[DEBUG] Click via JS OK")
            screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_js_click.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[DEBUG] Screenshot após JS click: {screenshot_nome}")
            return
        except Exception as e:
            print(f"[DEBUG] Falhou click via JS: {e}")

        # Tenta clicar por classname (como no exemplo do blog)
        try:
            class_name = element.get_attribute("class")
            if class_name:
                js = f"""
                var elems = document.getElementsByClassName('{class_name.split()[0]}');
                if(elems.length) elems[0].click();
                """
                driver.execute_script(js)
                print("[DEBUG] Click via JS por className OK")
                screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_js_class_click.png"
                driver.save_screenshot(screenshot_nome)
                print(f"[DEBUG] Screenshot após JS class click: {screenshot_nome}")
                return
        except Exception as e:
            print(f"[DEBUG] Falhou click via JS por className: {e}")

        # Tenta remover overlays comuns
        try:
            driver.execute_script("""
            let overlays = document.querySelectorAll('div[role=dialog], .modal, .overlay, .popup');
            overlays.forEach(el => el.parentNode.removeChild(el));
            """)
            print("[DEBUG] Overlays removidos por JS")
            time.sleep(0.5)
            element.click()
            print("[DEBUG] Click após remover overlays OK")
            screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_overlay_click.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[DEBUG] Screenshot após overlay click: {screenshot_nome}")
            return
        except Exception as e:
            print(f"[DEBUG] Falhou click após remover overlays: {e}")

        # Se ainda não funcionou, tenta novamente com JS após scroll extra
        try:
            driver.execute_script("window.scrollBy(0, 150);")
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", element)
            print("[DEBUG] Click via JS após scroll extra OK")
            screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_js_scroll_click.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[DEBUG] Screenshot após JS scroll click: {screenshot_nome}")
            return
        except Exception as e:
            print(f"[DEBUG] Falhou click via JS após scroll extra: {e}")

        raise Exception("Nenhuma estratégia de click funcionou para este elemento.")

    except Exception as e2:
        screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_erro.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[DEBUG] Erro ao clicar, screenshot: {screenshot_nome}")
        raise Exception(f"Safe click falhou por completo: {e2}")

def aceitar_cookies_se_existem(driver, screenshot_dir="fotos erros"):
    print("[DEBUG] A tentar aceitar cookies (com iframes)...")
    time.sleep(2)
    os.makedirs(screenshot_dir, exist_ok=True)
    textos = [
        'Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Consent', 'Agree', 'OK'
    ]
    # Tenta fora dos iframes
    for texto in textos:
        try:
            print(f"[DEBUG] A procurar botão fora de iframes: {texto}")
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(.,'{texto}')]"))
            )
            print(f"[DEBUG] Botão encontrado fora de iframe: {texto}")
            driver.save_screenshot(
                os.path.join(screenshot_dir, f"cookie_btn_out_{texto}_{int(time.time())}.png"))
            safe_click(driver, btn, screenshot_prefix=os.path.join(screenshot_dir, "cookie_out"))
            return
        except Exception as e:
            print(f"[DEBUG] Não encontrou botão '{texto}' fora de iframe: {e}")

    # Agora dentro dos iframes
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"[DEBUG] {len(iframes)} iframes encontrados.")
    for idx, iframe in enumerate(iframes):
        try:
            driver.switch_to.frame(iframe)
            for texto in textos:
                try:
                    print(f"[DEBUG] A procurar botão '{texto}' dentro de iframe {idx}")
                    btn = driver.find_element(By.XPATH, f"//button[contains(.,'{texto}')]")
                    print(f"[DEBUG] Botão '{texto}' encontrado dentro de iframe {idx}")
                    driver.save_screenshot(
                        os.path.join(screenshot_dir, f"cookie_btn_in_{texto}_{idx}_{int(time.time())}.png"))
                    safe_click(driver, btn, screenshot_prefix=os.path.join(screenshot_dir, f"cookie_in_{idx}"))
                    driver.switch_to.default_content()
                    return
                except Exception:
                    continue
            driver.switch_to.default_content()
        except Exception as e:
            print(f"[DEBUG] Erro ao procurar em iframe {idx}: {e}")
            driver.switch_to.default_content()
    print("[DEBUG] Nenhum botão de cookies encontrado (mesmo com iframes).")
    driver.save_screenshot(
        os.path.join(screenshot_dir, f"apos_cookies_{int(time.time())}.png"))

def clicar_noticias_tab(driver):
    print("[DEBUG] A tentar clicar no separador Notícias...")
    try:
        noticias_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'tbm=nws')]"))
        )
        print("[DEBUG] Tab de notícias encontrada!")
        safe_click(driver, noticias_tab, screenshot_prefix="noticias_tab")
        time.sleep(2)
        return True
    except Exception as e:
        screenshot_nome = f"erro_noticias_tab_{int(time.time())}.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[ERRO clicar_noticias_tab]: {e} (screenshot: {screenshot_nome})")
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    print(f"[DEBUG] A tentar aplicar filtro de tempo: {filtro_tempo}")
    try:
        btn_ferramentas = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Ferramentas']"))
        )
        print("[DEBUG] Botão Ferramentas encontrado.")
        safe_click(driver, btn_ferramentas, screenshot_prefix="ferramentas")
        time.sleep(1.3)
        btn_recentes = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Recentes']"))
        )
        print("[DEBUG] Botão Recentes encontrado.")
        safe_click(driver, btn_recentes, screenshot_prefix="recentes")
        time.sleep(1.3)

        menu_itens = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']"))
        )
        print(f"[DEBUG] {len(menu_itens)} itens no menu de filtro.")

        for item in menu_itens:
            print(f"[DEBUG] Item de menu: {item.text.strip()}")
            if filtro_tempo.strip().lower() in item.text.strip().lower():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.4)
                safe_click(driver, item, screenshot_prefix="menu_itemradio")
                break

        time.sleep(2)
    except Exception as e:
        screenshot_nome = f"erro_filtro_tempo_{int(time.time())}.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[ERRO filtro]: {e} (screenshot: {screenshot_nome})")

def clicar_linguagem(driver):
    print("[DEBUG] A tentar clicar para filtrar por língua...")
    try:
        pesquisar_div = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'KTBKoe') and contains(text(), 'Pesquisar na Web')]"))
        )
        print("[DEBUG] Div de pesquisa encontrada.")
        safe_click(driver, pesquisar_div, screenshot_prefix="pesquisar_linguagem")
        time.sleep(1.3)

        link_pt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Pesquisar páginas em Português')]"))
        )
        print("[DEBUG] Link para pesquisar em Português encontrado.")
        safe_click(driver, link_pt, screenshot_prefix="pesquisar_pt")
        time.sleep(1.0)
    except Exception as e:
        screenshot_nome = f"erro_linguagem_{int(time.time())}.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[ERRO clicar_linguagem]: {e} (screenshot: {screenshot_nome})")

def coletar_links_noticias(driver):
    print("[DEBUG] A recolher links das notícias...")
    try:
        blocos = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[@role='heading' and contains(@class,'n0jPhd')]"))
        )
        print(f"[DEBUG] {len(blocos)} blocos de notícia encontrados.")
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
                try:
                    data_parent = bloco.find_element(By.XPATH, "./../../..")
                    spans = data_parent.find_elements(By.XPATH, ".//span")
                    data_text = "N/D"
                    for span in spans:
                        texto = span.text.strip()
                        if re.match(r"^h\u00e1\s+\d+\s+(minuto|hora|dia|semana|m\u00eas|ano)s?$", texto):
                            data_text = texto
                            break
                        elif re.match(r"^\d{2}/\d{2}/\d{4}$", texto):
                            data_text = texto
                            break
                except Exception as e:
                    data_text = "N/D"
                links.append((href, data_text))
            except Exception as e:
                continue
        print(f"[DEBUG] {len(links)} links recolhidos.")
        return links
    except Exception as e:
        screenshot_nome = f"erro_coletar_links_{int(time.time())}.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[ERRO coletar_links_noticias]: {e} (screenshot: {screenshot_nome})")
        return []

def visitar_links(driver, links, keyword, resultados):
    print(f"[DEBUG] A visitar {len(links)} links de notícias...")
    for url, data_pub in links:
        try:
            print(f"[DEBUG] A visitar link: {url}")
            link_element = driver.find_element(By.XPATH, f"//a[@href='{url}']")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
            time.sleep(0.7)
            safe_click(driver, link_element, screenshot_prefix="visitar_link")
            time.sleep(4)

            possiveis_botoes = [
                "//button[contains(text(), 'Aceitar')]",
                "//button[contains(text(), 'Concordo')]",
                "//span[contains(text(),'Aceitar')]",
                "//span[contains(text(),'Concordo')]",
                "//span[contains(text(),'Consentir')]",
                "//button[contains(text(),'Consentir')]"
            ]
            for xpath in possiveis_botoes:
                try:
                    btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    safe_click(driver, btn, screenshot_prefix="btn_consentimento")
                    break
                except:
                    continue

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

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
            except:
                corpo = driver.page_source

            titulo = driver.title if driver.title else "Sem título"
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
            time.sleep(2.5)

        except Exception as e:
            ts = int(time.time())
            screenshot_nome = f"erro_visitar_link_{ts}.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[ERRO visitar_links]: {e} (screenshot: {screenshot_nome})")
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
                time.sleep(2)
            except:
                continue

def proxima_pagina(driver):
    print("[DEBUG] A tentar avançar para a próxima página de notícias...")
    try:
        next_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "pnnext"))
        )
        print("[DEBUG] Botão próxima página encontrado!")
        safe_click(driver, next_btn, screenshot_prefix="proxima_pagina")
        time.sleep(2.5)
        return True
    except Exception as e:
        screenshot_nome = f"erro_proxima_pagina_{int(time.time())}.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[ERRO proxima_pagina]: {e} (screenshot: {screenshot_nome})")
        return False

def executar_scraper_google(keyword, filtro_tempo):
    print("[DEBUG] A iniciar o scraper do Google...")
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1024")
    driver = uc.Chrome(options=options)
    driver.set_window_size(1280, 1024)
    resultados = []
    try:
        print("[DEBUG] A abrir o Google...")
        driver.get("https://www.google.com")
        aceitar_cookies_se_existem(driver)

        print(f"[DEBUG] A procurar campo de pesquisa...")
        search_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "q"))
        )
        time.sleep(1.3)
        print(f"[DEBUG] A escrever pesquisa: {keyword}")
        search_input.clear()
        search_input.send_keys(keyword)
        search_input.send_keys(Keys.ENTER)
        time.sleep(2.5)

        if clicar_noticias_tab(driver):
            aplicar_filtro_tempo(driver, filtro_tempo)
            clicar_linguagem(driver)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='heading']"))
            )
            while True:
                links = coletar_links_noticias(driver)
                if links:
                    visitar_links(driver, links, keyword, resultados)
                if not proxima_pagina(driver):
                    break
    finally:
        driver.quit()
    print("[DEBUG] Scraper terminado.")
    return resultados

def rodar_scraper_sequencial(keywords_string, filtro_tempo):
    print("[DEBUG] Scraper sequencial iniciado.")
    all_results = []
    keywords = [kw.strip() for kw in keywords_string.split(",") if kw.strip()]
    for kw in keywords:
        print(f"[DEBUG] A pesquisar keyword: {kw}")
        try:
            resultados = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(resultados)
        except Exception as e:
            print(f"[ERRO geral]: {e}")
            all_results.append({
                "link": "",
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": "",
                "erro": str(e),
                "keyword": kw
            })
    print("[DEBUG] Scraper sequencial terminado.")
    return all_results

if __name__ == "__main__":
    print("[DEBUG] Script iniciado.")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas'): ")
    print("[DEBUG] Antes de rodar o scraper.")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    print("[DEBUG] Depois de rodar o scraper.")
    print(resultados)
    print("[DEBUG] Ficheiros finais:", os.listdir("."))