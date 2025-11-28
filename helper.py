import json
from os import listdir, makedirs
from os.path import dirname, exists, expanduser
from shutil import rmtree
from zipfile import ZipFile

import requests
from termcolor import colored

MC_DIR = f"{expanduser('~')}/.minecraft"

session = requests.session()


def download_file(url: str, dest: str):
    if not exists(dirname(dest)):
        makedirs(dirname(dest), exist_ok=True)
    with session.get(url, stream=True) as r:
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024 * 8):
                f.write(chunk)


def extract(file: str, extr_dir: str):
    if exists(f"/tmp/{extr_dir}"):
        rmtree(f"/tmp/{extr_dir}")
    with ZipFile(file, "r") as z:
        z.extractall(f"/tmp/{extr_dir}")


def get_modpacks():
    return listdir(f"{MC_DIR}/instances")


def confirm(txt: str):
    return input(f"{txt} [y/n] -> ") in ["Y", "y", ""]


def choose(lst: list, stuff: str = "stuff"):
    if len(lst) <= 0:
        print(colored(f"no {stuff}s installed!", "yellow"))
    for num, i in enumerate(lst):
        print(f"[{num + 1}] {i}")

    return lst[int(input("choose -> ")) - 1]


def save_json(file: str, js):
    with open(file, "w") as f:
        json.dump(js, f, indent=2)


def load_json(file: str):
    with open(file, "r") as f:
        return json.load(f)


def get_modrinth_index(folder="/tmp/modpack/"):
    with open(f"{folder}/modrinth.index.json", "r") as f:
        return json.load(f)
