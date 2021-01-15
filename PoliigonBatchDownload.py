import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import sys
import os
import asyncio
from time import sleep
from time import perf_counter
from termcolor import colored
from queue import Queue, SimpleQueue
import fuckit
import yaml
import wget

"""
By - Axel Roijers

Demo: https://www.youtube.com/watch?v=5g7abM-lVTU

I made this script because i lost my entire poliigon library and didn't want to download them by hand,
It's a work in progress and hacky at best.
I am not putting a lot of time into this because that would defeat it's purpose.
Entire parts are missing/disabled for now, (it skips models because I didn't need them for now)
but it hopefully saves someone and evening of work


Here's how it works
1. opens a chorme window and logs into your poliigon account
2. collects links to all your assets
3. excludes the ones already downloaded
4. open 8 more windows logs into them
5. selects the right resolution and presses download
6. switch to another chrome window to start the next download

I open multiple chrome windows because single poliigon sessions seem to have a bitrate cap around 20-30Mbps

"""

# Config
try:
    config_path = sys.argv[1]
except:
    config_path = "config.yaml"

with open(config_path, "r") as f:
    config = yaml.load(f.read())

if config["PASSWORD"] == "":
    config["PASSWORD"] = input("Enter password")

LOGIN = config["LOGIN"]
PASSWORD = config["PASSWORD"]
N_WORKERS = config["N_WORKERS"]
DOWNLOAD_INIT_TIMEOUT = config["DOWNLOAD_INIT_TIMEOUT"]
DOWNLOAD_PATH = config["DOWNLOAD_PATH"]

if not os.path.isfile("Dark-Reader-4.9.26.crx"):
    wget.download("https://www.crx4chrome.com/go.php?p=1057&s=1&l=https%3A%2F%2Fclients2.googleusercontent.com%2Fcrx%2Fblobs%2FQgAAAC6zw0qH2DJtnXe8Z7rUJP0NxkjBCer3r-p92OanYpzE1erojdesVovPZnqmwjCIvjiP0s_4j0VyVnbcBDcwD4yNJQPD-zfEkeWpVdMmXUsMAMZSmuXbQkwjC4jLGZLXH6oy3nZtN-KiHg%2Fextension_4_9_26_0.crx","Dark-Reader-4.9.26.crx")
DARK_READER_PATH = os.path.abspath("Dark-Reader-4.9.26.crx")

# Download
os.chdir(DOWNLOAD_PATH)

def find_element(driver, query, type):
    element = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((type, query))
    )
    return element


def find_elements(driver, query, type):
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((type, query)))
    sleep(0.25)
    elements = driver.find_elements(type, query)
    return elements


def set_multi_option(options: list, enabled_options: list):
    for op in options:
        text = op.text
        is_enabled = (
            False
            if op.find_element_by_tag_name("a").get_attribute("aria-selected")
            == "false"
            else True
        )
        if is_enabled != (text in enabled_options):
            op.click()
            sleep(0.4)


# %% setup download path launch chrome
def make_new_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.set_capability("requireWindowFocus", True)
    prefs = {"download.default_directory": DOWNLOAD_PATH}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_extension(DARK_READER_PATH)
    driver = webdriver.Chrome(chrome_options=chrome_options)

    # %% Log in to poliigon
    driver.get("https://www.poliigon.com/login")
    sleep(1)
    # login
    print("login: email")
    elem = find_element(driver, "email", By.NAME)
    elem.clear()
    elem.send_keys(LOGIN)

    print("login: password")
    elem = find_element(driver, "password", By.NAME)
    elem.clear()
    elem.send_keys(PASSWORD)
    sleep(1)
    find_element(
        driver,
        '//*[@id="app"]/div/section/div/div/div/div/div/div/form/div[3]/div[2]/div/div/input',
        By.XPATH,
    ).click()
    # sleep to fully log in
    sleep(5)
    return driver


# Phase 1: go to my assets and find all the links
if not os.path.isfile("poliigon_links.txt"):
    print("No link file found, searching for links")
    links = []
    driver = make_new_driver()
    driver.get(
        "https://www.poliigon.com/search?type=all&refine_by=assets-myassets"
    )  # finding all links
    try:
        while True:
            sleep(0.25)
            linkelements = find_elements(driver, "deadLink", By.CLASS_NAME)
            print("found:", len(linkelements))
            links.extend([elem.get_attribute("href") for elem in linkelements])
            print("total:", len(links))

            element = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="pagination"]/div/ul/li[10]/a')
                )
            )
            sleep(0.25)
            element.click()

    except selenium.common.exceptions.TimeoutException:
        print("end of pages")

    driver.quit()
    file = open("poliigon_links.txt", "w")
    for link in links:
        file.write(link)
        file.write("\n")
    file.close()

else:
    with open("poliigon_links.txt", "r") as f:
        links = [link[:-1] for link in f.readlines()]
    print(f"found {len(links)} links skipping phase 1")


# longass function
filenames = [
    "".join([word.capitalize() for word in link.split("/")[-1].split("-")])
    for link in links
]

todos = SimpleQueue()
[
    todos.put((link, filename))
    for link, filename in zip(links, filenames)
    if not os.path.exists(f"{DOWNLOAD_PATH}\{filename}.zip")
]

print(f"Kept {todos.qsize()} out of {len(links)}")

#%% Phase 2: download all the files
@fuckit
def find_download_btn(driver):

    downloadbtn = WebDriverWait(driver, 4).until(
        EC.visibility_of_element_located((By.ID, "express_download"))
    )

    downloadbtn = WebDriverWait(driver, 4).until(
        EC.visibility_of_element_located((By.ID, "free_download"))
    )

    return downloadbtn



software_options_xpath = '//*[@id="3d_softwares"]/div[2]/div/'
renderer_options_xpath = '//*[@id="renders"]/div[2]/div/'
renderer_options_xpath = '//*[@id="texture_sizes"]/div[2]/div/'

def make_options_xpath(option:str):
    xpath = f'//*[@id={option}]/div[2]/div/'


async def new_worker(queue: SimpleQueue):

    driver = make_new_driver()

    while True:
        if queue.empty():
            driver.quit()
            break
        next_download = queue.get_nowait()
        url, filename = next_download
        print(filename)
        driver.get(url)
        sleep(3)

        if "model" in driver.current_url:
            continue

            # press 3D software options
            find_element(
                driver,
                make_options_xpath("3d_softwares")+"button",
                By.XPATH,
            ).click()
            sleep(0.25)

            software_options = find_element(
                driver,
                make_options_xpath("3d_softwares")+"div/ul",
                By.XPATH,
            ).find_elements_by_tag_name("li")
            

            # press RendererOptions
            find_element(
                driver,
                make_options_xpath("renders")+"button",
                By.XPATH,
            ).click()
            sleep(0.25)
            renderer_options = find_element(
                driver,
                make_options_xpath("renders")+"div/ul",
                By.XPATH,
            ).find_elements_by_tag_name("li")
            set_multi_option()




            # press ExtraTextureSizes
            texture_options = find_element(
                driver,
                '//*[@id="3d_softwares"]/div[2]/div/div/ul',
                By.XPATH,
            ).find_elements_by_tag_name("li")





            find_element(
                driver,
                '//*[@id="3d_softwares"]/div[2]/div/div/ul/li[2]/a/span[1]',
                By.XPATH,
            ).click()
            sleep(0.25)

            find_element(
                driver, '//*[@id="texture_sizes"]/div[2]/div/button', By.XPATH
            ).click()
            sleep(0.25)
            res_options = find_element(
                driver, '//*[@id="texture_sizes"]/div[2]/div/div/ul', By.XPATH
            ).find_elements_by_tag_name("li")
            res_options[-1].click()

            set_multi_option(res_options, config["texture-sizes"])
            sleep(0.25)

        elif "texture" in driver.current_url:
            
            # if texture

            dropdown = find_element(
                driver,
                '//*[@id="acquared-asset"]/div[5]/div/div[2]/div[2]/div/button',
                By.XPATH,
            )
            dropdown.click()
            sleep(0.25)
            res_options = find_element(
                driver,
                '//*[@id="acquared-asset"]/div[5]/div/div[2]/div[2]/div/div/ul',
                By.XPATH,
            ).find_elements_by_tag_name("li")

            set_multi_option(res_options, config["texture-sizes"])

            dropdown.click()
            sleep(0.5)

        elif "hdr" in driver.current_url:
            # if texture

            dropdown = find_element(
                driver,
                '//*[@id="acquared-asset"]/div[5]/div/div[2]/div[2]/div/button',
                By.XPATH,
            )
            dropdown.click()
            sleep(0.5)
            res_options = find_element(
                driver,
                '//*[@id="acquared-asset"]/div[5]/div/div[2]/div[2]/div/div/ul',
                By.XPATH,
            ).find_elements_by_tag_name("li")

            set_multi_option(res_options, config["hdr-sizes"])

            dropdown.click()
            sleep(0.5)

        find_download_btn(driver).click()
        t1 = perf_counter()
        sleep(3)

        while not (
            os.path.exists(f"{DOWNLOAD_PATH}\{filename}.zip")
            or os.path.exists(f"{DOWNLOAD_PATH}\{filename}.crdownload")
            or os.path.exists(f"{DOWNLOAD_PATH}\{filename}.zip.crdownload")
        ):
            elapsed = perf_counter() - t1
            print(
                filename,
                colored(
                    f" waiting on{filename} | {int(elapsed)}/{DOWNLOAD_INIT_TIMEOUT}",
                    "yellow",
                ),
            )
            if elapsed > DOWNLOAD_INIT_TIMEOUT:
                print(filename, colored(f" Failed or timed out {filename}", "red"))
                break
            sleep(1)

        print(filename, colored(f"started downloading {filename}", "cyan"))
        driver.minimize_window()

        while not os.path.exists(f"{DOWNLOAD_PATH}\{filename}.zip"):

            print(filename, colored(f"downloading {filename}", "blue"))
            await asyncio.sleep(5)

        print(filename, colored(f" finished downloading{filename}", "green"))
        driver.maximize_window()


async def main():
    await asyncio.gather(*[new_worker(todos) for _ in range(N_WORKERS)])


asyncio.run(main())
print("finished downloading")
# %% Unzip


