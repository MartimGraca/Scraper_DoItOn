import time
import re
from urllib.parse import urlparse, urlunparse

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Helper for robust clicking
def safe_click(driver, element, screenshot_prefix="erro_click"):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.2)
        print("displayed:", element.is_displayed(), "enabled:", element.is_enabled())
        driver.save_screenshot(f"{screenshot_prefix}_{int(time.time())}_antes.png")
        element.click()
    except Exception as e:
        try:
            print("Falhou click normal, a tentar JS click...")
            driver.save_screenshot(f"{screenshot_prefix}_{int(time.time())}_js.png")
            driver.execute_script("arguments[0].click();", element)
        except Exception as e2:
            driver.save_screenshot(f"{screenshot_prefix}_{int(time.time())}_erro.png")
            print("Erro ao clicar, ver screenshot!")
            raise Exception(f"Safe click falhou: {e} / {e2}")

def aceitar_cookies_se_existem(driver):
    time.sleep(2)
    textos = ['Aceitar tudo', 'Accept all', 'Aceitar', 'Concordo', 'Accept all']
    for texto in textos:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(.,'{texto}')]"))
            )
            safe_click(driver, btn, screenshot_prefix="aceitar_cookies")
            time.sleep(1)
            break
        except:
            continue

def clicar_noticias_tab(driver):
    try:
        noticias_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'tbm=nws')]"))
        )
        safe_click(driver, noticias_tab, screenshot_prefix="noticias_tab")
        time.sleep(2)
        return True
    except Exception as e:
        driver.save_screenshot(f"erro_noticias_tab_{int(time.time())}.png")
        print("[ERRO clicar_noticias_tab]:", e)
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    try:
        btn_ferramentas = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Ferramentas']"))
        )
        safe_click(driver, btn_ferramentas, screenshot_prefix="ferramentas")
        time.sleep(1.3)
        btn_recentes = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Recentes']"))
        )
        safe_click(driver, btn_recentes, screenshot_prefix="recentes")
        time.sleep(1.3)

        menu_itens = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']"))
        )

        for item in menu_itens:
            if filtro_tempo.strip().lower() in item.text.strip().lower():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.4)
                safe_click(driver, item, screenshot_prefix="menu_itemradio")
                break

        time.sleep(2)
    except Exception as e:
        driver.save_screenshot(f"erro_filtro_tempo_{int(time.time())}.png")
        print(f"[ERRO filtro]: {e}")

def clicar_linguagem(driver):
    try:
        pesquisar_div = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'KTBKoe') and contains(text(), 'Pesquisar na Web')]"))
        )
        safe_click(driver, pesquisar_div, screenshot_prefix="pesquisar_linguagem")
        time.sleep(1.3)

        link_pt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Pesquisar páginas em Português')]"))
        )
        safe_click(driver, link_pt, screenshot_prefix="pesquisar_pt")
        time.sleep(1.0)
    except Exception as e:
        driver.save_screenshot(f"erro_linguagem_{int(time.time())}.png")
        print(f"[ERRO clicar_linguagem]: {e}")

def coletar_links_noticias(driver):
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
                except:
                    data_text = "N/D"
                links.append((href, data_text))
            except:
                continue
        return links
    except Exception as e:
        driver.save_screenshot(f"erro_coletar_links_{int(time.time())}.png")
        print("[ERRO coletar_links_noticias]:", e)
        return []

def visitar_links(driver, links, keyword, resultados):
    for url, data_pub in links:
        try:
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
            driver.save_screenshot(f"erro_visitar_link_{ts}.png")
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
    try:
        next_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "pnnext"))
        )
        safe_click(driver, next_btn, screenshot_prefix="proxima_pagina")
        time.sleep(2.5)
        return True
    except Exception as e:
        driver.save_screenshot(f"erro_proxima_pagina_{int(time.time())}.png")
        print("[ERRO proxima_pagina]:", e)
        return False

def executar_scraper_google(keyword, filtro_tempo):
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--headless=new")  # novo headless, mais robusto
    options.add_argument("--window-size=1280,1024")
    driver = uc.Chrome(options=options)
    driver.set_window_size(1280, 1024) # redundante, mas garante
    resultados = []
    try:
        driver.get("https://www.google.com")
        aceitar_cookies_se_existem(driver)

        search_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "q"))
        )
        time.sleep(1.3)
        for letra in keyword:
            search_input.send_keys(letra)
            time.sleep(0.21)
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
    return resultados

def rodar_scraper_sequencial(keywords_string, filtro_tempo):
    all_results = []
    keywords = [kw.strip() for kw in keywords_string.split(",") if kw.strip()]
    for kw in keywords:
        try:
            resultados = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(resultados)
        except Exception as e:
            all_results.append({
                "link": "",
                "titulo": "Erro",
                "site": "Erro",
                "status": "ERRO",
                "data": "",
                "erro": str(e),
                "keyword": kw
            })
    return all_results

if _name_ == "_main_":
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas'): ")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    print(resultados)