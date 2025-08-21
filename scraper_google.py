import os
import re
import time
from urllib.parse import urlparse
import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================= Config =================
HEADLESS = os.getenv("HEADLESS", "0") == "1"   # export HEADLESS=1 para headless
UC_VERSION_MAIN = os.getenv("UC_VERSION_MAIN") # ex.: "137" (como no teu localhost)
SCREENSHOT_DIR = "fotos_erros"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    print(f"[{ts}] {msg}", flush=True)

def save_shot(driver, name):
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        driver.save_screenshot(path)
        log(f"[DEBUG] Screenshot guardada: {path}")
    except Exception as e:
        log(f"[DEBUG] Falhou screenshot: {e}")

def save_html(driver, name):
    path = os.path.join(SCREENSHOT_DIR, name)
    try:
        html = driver.page_source
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"[DEBUG] HTML guardado: {path}")
    except Exception as e:
        log(f"[DEBUG] Falhou HTML dump: {e}")

# ================ Cookies ==================
def aceitar_cookies_se_existem(driver):
    time.sleep(2.0)
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button//div[normalize-space(text())='Aceitar tudo']"))
        )
        btn.click()
        return
    except Exception:
        pass
    # fallbacks simples
    candidatos = [
        "//button[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
        "//div[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
        "//span[contains(translate(., 'ACEITAR', 'aceitar'),'aceitar')]",
        "//button[contains(@aria-label, 'Accept')]",
    ]
    for xp in candidatos:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            break
        except Exception:
            continue

# ============== Navegação Google ============
def clicar_noticias_tab(driver):
    try:
        tab = WebDriverWait(driver, 12).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'tbm=nws')]"))
        )
        tab.click()
        time.sleep(2)
        return True
    except Exception:
        return False

def aplicar_filtro_tempo(driver, filtro_tempo):
    if not filtro_tempo:
        return
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Ferramentas']"))
        ).click()
        time.sleep(1.0)
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[normalize-space()='Recentes']"))
        ).click()
        time.sleep(1.0)
        itens = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//a[@role='menuitemradio']"))
        )
        alvo_txt = filtro_tempo.strip().lower()
        for item in itens:
            try:
                if alvo_txt in item.text.strip().lower():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", item)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", item)
                    break
            except Exception:
                continue
        time.sleep(1.5)
    except Exception as e:
        log(f"[ERRO filtro]: {e}")

def clicar_linguagem(driver):
    # Só se aparecer
    try:
        pesquisar_div = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'KTBKoe') and contains(.,'Pesquisar na Web')]"))
        )
        pesquisar_div.click()
        time.sleep(0.8)
        link_pt = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(.,'Pesquisar páginas em Português')]"))
        )
        link_pt.click()
        time.sleep(1.0)
    except Exception:
        pass

# ============== Coleta/Visita ===============
def coletar_links_noticias(driver):
    """
    Mantém a tua regra original e adiciona seletores típicos do tbm=nws.
    Regras de aceitar link:
      - href começa por 'http' OU por '/url' (Google redireciona)
    """
    log("[DEBUG] A recolher links...")
    links = []
    seen = set()

    # Estratégias (ordem de prioridade)
    strategies = [
        # Tua regra original: div[@role='heading' and contains(@class,'n0jPhd')] -> ancestor::a[1]
        ("blocos_heading", "//div[@role='heading' and contains(@class,'n0jPhd')]"),
        # Muito comum em tbm=nws
        ("dbsr", "//div[contains(@class,'dbsr')]//a[@href]"),
        # Âncoras com h3
        ("a_h3", "//a[.//h3]"),
        # Âncoras com role=heading
        ("a_role_heading", "//a[.//div[@role='heading']]"),
        # Classes vistas no News SERP
        ("class_WlydOe", "//a[contains(@class,'WlydOe')]"),
        ("class_tHmfQe", "//a[contains(@class,'tHmfQe')]"),
    ]

    for name, xp in strategies:
        try:
            elems = driver.find_elements(By.XPATH, xp)
        except Exception:
            elems = []
        if not elems:
            continue

        if name == "blocos_heading":
            # Sobe ao ancestor::a[1]
            for bloco in elems:
                try:
                    a_el = bloco.find_element(By.XPATH, ".//ancestor::a[1]")
                    href = a_el.get_attribute("href") or ""
                    if not href:
                        continue
                    if not (href.startswith("http") or href.startswith("/url")):
                        continue
                    # Extrair data
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
        else:
            # Estratégias que já devolvem anchors
            for a_el in elems:
                try:
                    href = a_el.get_attribute("href") or ""
                    if not href:
                        continue
                    if not (href.startswith("http") or href.startswith("/url")):
                        continue

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
                    seen.add(key)
                    links.append((href, data_text))
                except Exception:
                    continue

        if links:
            break  # já encontrámos via uma estratégia

    log(f"[DEBUG] {len(links)} links recolhidos.")
    if not links:
        save_shot(driver, f"no_results_{int(time.time())}.png")
        save_html(driver, f"no_results_{int(time.time())}.html")
    return links

def visitar_links(driver, links, keyword, resultados):
    for href, data_pub in links:
        try:
            # Tenta localizar o anchor com o href exato
            link_element = None
            try:
                link_element = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[@href='{href}']"))
                )
            except Exception:
                # fallback: starts-with (tracking dinâmico)
                base = href.split("&")[0].replace("'", "\\'")
                try:
                    link_element = WebDriverWait(driver, 4).until(
                        EC.element_to_be_clickable((By.XPATH, f"//a[starts-with(@href, '{base}')]"))
                    )
                except Exception:
                    link_element = None

            if link_element:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_element)
                time.sleep(0.8)
                link_element.click()
            else:
                driver.get(href)  # última alternativa
            time.sleep(3.0)

            # aceitar cookies do site (básico)
            for xp in [
                "//button[contains(., 'Aceitar')]",
                "//button[contains(., 'Concordo')]",
                "//span[contains(.,'Aceitar')]",
                "//span[contains(.,'Concordo')]",
                "//span[contains(.,'Consentir')]",
                "//button[contains(.,'Consentir')]",
            ]:
                try:
                    btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
                    btn.click()
                    break
                except Exception:
                    continue

            # scroll leve
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)

            # recolha de texto
            try:
                artigos = driver.find_elements(By.TAG_NAME, "article")
                if artigos:
                    corpo = " ".join([a.text for a in artigos if a.text.strip()])
                else:
                    divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'content') or contains(@class, 'article')]")
                    corpo = " ".join([d.text for d in divs if d.text.strip()])
                if not corpo:
                    corpo = driver.page_source
            except Exception:
                corpo = driver.page_source

            titulo = driver.title or "Sem título"
            site = urlparse(driver.current_url).netloc
            encontrou = keyword.lower() in corpo.lower()
            status = "ENCONTRADA" if encontrou else "NÃO ENCONTRADA"

            resultados.append({
                "link": driver.current_url,
                "titulo": titulo,
                "site": site,
                "status": status,
                "data": data_pub
            })

            driver.back()
            time.sleep(2.0)
        except Exception as e:
            resultados.append({
                "link": href,
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
    try:
        WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.ID, "pnnext"))
        ).click()
        time.sleep(1.5)
        return True
    except Exception:
        # fallback por parâmetro start
        try:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(driver.current_url)
            qs = parse_qs(parsed.query)
            start = int(qs.get("start", ["0"])[0])
            qs["start"] = [str(start + 10)]
            newq = urlencode({k: v[0] if isinstance(v, list) else v for k, v in qs.items()})
            new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, newq, parsed.fragment))
            driver.get(new_url)
            time.sleep(1.2)
            return True
        except Exception:
            return False

# ============== Runner principal =============
def executar_scraper_google(keyword, filtro_tempo):
    log("[DEBUG] A iniciar (1 ficheiro, fluxo antigo + coleta robusta).")

    options = uc.ChromeOptions()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--disable-extensions")
    options.add_argument("--log-level=2")
    options.add_argument("--lang=pt-PT")

    # criar driver
    if UC_VERSION_MAIN:
        driver = uc.Chrome(options=options, version_main=int(UC_VERSION_MAIN))
    else:
        try:
            driver = uc.Chrome(options=options, version_main=137)
        except Exception:
            driver = uc.Chrome(options=options)

    resultados = []
    try:
        driver.get("https://www.google.com")
        aceitar_cookies_se_existem(driver)

        # pesquisar (teu fluxo original)
        search_input = WebDriverWait(driver, 12).until(
            EC.element_to_be_clickable((By.NAME, "q"))
        )
        time.sleep(0.8)
        for letra in keyword:
            search_input.send_keys(letra)
            time.sleep(0.18)
        search_input.send_keys(Keys.ENTER)
        time.sleep(1.8)

        if clicar_noticias_tab(driver):
            aplicar_filtro_tempo(driver, filtro_tempo)
            clicar_linguagem(driver)

            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='heading']"))
                )
            except Exception:
                pass

            while True:
                links = coletar_links_noticias(driver)
                if links:
                    visitar_links(driver, links, keyword, resultados)
                if not proxima_pagina(driver):
                    break
        else:
            log("[DEBUG] Não foi possível abrir o separador Notícias.")
            save_shot(driver, "no_news_tab.png")
            save_html(driver, "no_news_tab.html")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return resultados

def rodar_scraper_sequencial(keywords_string, filtro_tempo):
    all_results = []
    keywords = [k.strip() for k in keywords_string.split(",") if k.strip()]
    for kw in keywords:
        log(f"[DEBUG] A processar '{kw}'")
        try:
            res = executar_scraper_google(kw, filtro_tempo)
            all_results.extend(res)
        except Exception as e:
            log(f"[ERRO ao processar '{kw}']: {e}")
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

if __name__ == "__main__":
    kws = input("Palavras-chave separadas por vírgula: ")
    filtro = input("Filtro de tempo (ex.: Última hora, Últimas 24 horas, Última semana, Último mês, Último ano): ")
    out = rodar_scraper_sequencial(kws, filtro)
    log(str(out))