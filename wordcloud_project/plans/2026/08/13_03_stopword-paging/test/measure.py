import os
import json
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=1200,900')
opts.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

driver = webdriver.Chrome(options=opts)
try:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "repro_pagination.html")
    url = "file:///" + path.replace("\\", "/")
    driver.get(url)
    result = driver.execute_script("return window.__REPRO_RESULT__")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    out_path = os.path.join(here, "measure_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
finally:
    driver.quit()
