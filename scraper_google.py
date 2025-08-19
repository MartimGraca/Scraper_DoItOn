from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

options = Options()
# Para headless, descomenta a linha abaixo:
# options.add_argument("--headless=new")
options.add_argument("--window-size=1280,1024")
# Não adiciona --user-data-dir!

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://www.google.com")
    time.sleep(2)

    # Aceitar cookies se aparecer
    try:
        aceitar = driver.find_element(By.XPATH, "//button[.//div[contains(text(),'Aceitar') or contains(text(),'Accept')]]")
        aceitar.click()
        time.sleep(1)
    except Exception:
        pass

    search_box = driver.find_element(By.NAME, "q")
    search_box.click()
    print("Barra de pesquisa clicada com sucesso!")
    time.sleep(3)
finally:
    driver.quit()