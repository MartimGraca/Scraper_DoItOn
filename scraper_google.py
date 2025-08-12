import time
from urllib.parse import urlparse, urlunparse
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
import re
import os

def aceitar_cookies_se_existem(driver):
    time.sleep(3)
    try:
        aceitar_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button//div[text()='Aceitar tudo']"))
        )
        aceitar_btn.click()
    except:
        pass

def clicar_noticias_tab(driver):
    try:
        noticias_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'tbm=nws')]"))
        )
        noticias_tab.click()
        time.sleep(2)
        return True
    except:
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Ferramentas']"))
        ).click()
        time.sleep(1.5)
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[text()='Recentes']"))
        ).click()
        time.sleep(1.5)

        menu_itens = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']"))
        )

        for item in menu_itens:
            if filtro_tempo.strip().lower() in item.text.strip().lower():
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", item)
                break

        time.sleep(3)
    except Exception as e:
        print(f"[ERRO filtro]: {e}")

def clicar_linguagem(driver):
    try:
        pesquisar_div = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'KTBKoe') and contains(text(), 'Pesquisar na Web')]"))
        )
        pesquisar_div.click()
        time.sleep(1.5)

        link_pt = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Pesquisar páginas em Português')]"))
        )
        link_pt.click()
        time.sleep(1.5)

    except Exception as e:
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
                clean_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
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
    except:
        return []

def visitar_links(driver, links, keyword, resultados):
    for url, data_pub in links:
        try:
            link_element = driver.find_element(By.XPATH, f"//a[@href='{url}']")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
            time.sleep(1)
            link_element.click()
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
                    btn.click()
                    break
                except:
                    continue

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

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
            time.sleep(3)

        except Exception as e:
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
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "pnnext"))
        ).click()
        time.sleep(3)
        return True
    except:
        return False

def executar_scraper_google(keyword, filtro_tempo):
   def executar_scraper_google(keyword, filtro_tempo):
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    # Podes adicionar headless se quiseres (mas testa sem primeiro):
    # options.add_argument("--headless=new")

    chrome_path = os.getenv("CHROME_BINARY", "/usr/bin/google-chrome")
    driver = uc.Chrome(options=options, browser_executable_path=chrome_path)
    if not chrome_path or not isinstance(chrome_path, str) or not chrome_path.strip():
        raise RuntimeError("CHROME_BINARY não definido ou inválido.")

    # Passa o path explicitamente!
    driver = uc.Chrome(options=options, browser_executable_path=chrome_path)
    resultados = []
    try:
        driver.get("https://www.google.com")
        aceitar_cookies_se_existem(driver)
        search_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "q"))
        )
        time.sleep(2)
        for letra in keyword:
            search_input.send_keys(letra)
            time.sleep(0.25)
        search_input.send_keys(Keys.ENTER)
        time.sleep(3)
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