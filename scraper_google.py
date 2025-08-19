import os
print("[DEBUG] INÍCIO DO SCRIPT")
print("[DEBUG] Working dir:", os.getcwd())
print("[DEBUG] Ficheiros atuais:", os.listdir("."))

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
        print(f"[DEBUG] A tentar dar scroll para o elemento {element}...")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.2)
        print(f"[DEBUG] Displayed: {element.is_displayed()}, Enabled: {element.is_enabled()}")
        screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_antes.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[DEBUG] Screenshot ANTES do click: {screenshot_nome}")
        element.click()
        screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_depois.png"
        driver.save_screenshot(screenshot_nome)
        print(f"[DEBUG] Screenshot DEPOIS do click: {screenshot_nome}")
        print("[DEBUG] Ficheiros após click:", os.listdir("."))
    except Exception as e:
        try:
            print("[DEBUG] Falhou click normal, a tentar JS click...")
            screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_js_antes.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[DEBUG] Screenshot ANTES do JS click: {screenshot_nome}")
            driver.execute_script("arguments[0].click();", element)
            screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_js_depois.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[DEBUG] Screenshot DEPOIS do JS click: {screenshot_nome}")
            print("[DEBUG] Ficheiros após JS click:", os.listdir("."))
        except Exception as e2:
            screenshot_nome = f"{screenshot_prefix}_{int(time.time())}_erro.png"
            driver.save_screenshot(screenshot_nome)
            print(f"[DEBUG] Erro ao clicar, screenshot: {screenshot_nome}")
            print("[DEBUG] Ficheiros após erro:", os.listdir("."))
            raise Exception(f"Safe click falhou: {e} / {e2}")

# ... resto do teu código ...

if __name__ == "__main__":
    print("[DEBUG] Script iniciado.")
    keywords = input("Palavras-chave separadas por vírgula: ")
    filtro_tempo = input("Filtro de tempo (ex: 'Última hora', 'Últimas 24 horas'): ")
    print("[DEBUG] Antes de rodar o scraper.")
    resultados = rodar_scraper_sequencial(keywords, filtro_tempo)
    print("[DEBUG] Depois de rodar o scraper.")
    print(resultados)
    print("[DEBUG] Ficheiros finais:", os.listdir("."))