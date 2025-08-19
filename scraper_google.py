from selenium import webdriver
import time

driver = webdriver.Chrome()
driver.get("https://www.google.com")
time.sleep(2)
driver.save_screenshot("teste_screenshot.png")
print("Screenshot guardada!")
driver.quit()