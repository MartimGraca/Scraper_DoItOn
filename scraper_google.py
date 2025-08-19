from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time

# Configurações do Chrome
options = Options()
# Para headless, descomenta a linha abaixo:
# options.add_argument("--headless=new")
options.add_argument("--window-size=1280,1024")

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://www.google.com")
    time.sleep(2)  # Espera a página carregar

    # Aceitar cookies se aparecer (não crasha se não encontrar)
    try:
        aceitar = driver.find_element(By.XPATH, "//button[.//div[contains(text(),'Aceitar') or contains(text(),'Accept')]]")
        aceitar.click()
        time.sleep(1)
    except:
        pass

    # Encontrar o campo de pesquisa e clicar nele
    search_box = driver.find_element(By.NAME, "q")
    search_box.click()
    print("Barra de pesquisa clicada com sucesso!")

    # Só para veres o resultado (tira ou ajusta o tempo como quiseres)
    time.sleep(3)
finally:
    driver.quit()