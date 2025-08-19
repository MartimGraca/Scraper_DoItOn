from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--window-size=1280,1024")

driver = webdriver.Chrome(options=options)
driver.get("https://www.google.com")
# resto do código...