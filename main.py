import json
from os import makedirs
from os.path import expanduser
from time import time
from zipfile import ZipFile

import requests

MC_DIR = f"{expanduser('~')}/.minecraft"


session = requests.Session()


def download_file(url: str, dest: str, session=session):
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024 * 8):
                f.write(chunk)


def extract_modpack(file):
    with ZipFile(file, "r") as z:
        z.extractall("/tmp/modpack")


def get_modrinth_index():
    with open("/tmp/modpack/modrinth.index.json", "r") as f:
        return json.load(f)


def install_modpack():
    st = time()
    data = get_modrinth_index()
    name = data["name"]
    files = data["files"]
    dir = f"{MC_DIR}/instances/{name}"
    makedirs(f"{dir}/mods", exist_ok=True)
    downloads = {}
    for i in files:
        if i["downloads"][0].endswith(".jar"):
            downloads[i["downloads"][0]] = f"{dir}/{i['path']}"

    for num, i in enumerate(downloads):
        print(f"[{num + 1}/{len(downloads)}] downloading {i.split('/')[-1]}")
        download_file(i, downloads[i])

    print(f"downloaded mods in {round(time() - st, 2)}!")


def search_modrinth(type=None, version=None):
    if type is None:
        types = ["mod", "modpack"]
        for num, t in enumerate(types):
            print(f"[{num + 1}] {t}")
        type = types[int(input("choose -> ")) - 1]
    if version is None:
        version = input("mc version -> ")
    query = input("search modrinth -> ")
    params = {
        "query": query,
        "facets": f'[["project_type:{type}"], ["categories:fabric"], ["versions:{version}"]]',
    }

    response = requests.get("https://api.modrinth.com/v2/search", params=params)
    r_data = response.json()
    hits = r_data["hits"]
    if len(hits) <= 0:
        print(f"no {type}s found")
        search_modrinth(type, version)

    for num, hit in enumerate(hits):
        print(f"[{num + 1}] {hit['title']} - {hit['project_type']}")

    choice = int(input("choose -> ")) - 1

    project_id = hits[choice]["project_id"]

    versions = requests.get(
        f"https://api.modrinth.com/v2/project/{project_id}/version"
    ).json()

    for v in versions:
        if "fabric" in v["loaders"] and version in v["game_versions"]:
            file_url = v["files"][0]["url"]
            file_name = v["files"][0]["filename"]
            download_file(file_url, f"/tmp/{file_name}")
            if type == "modpack":
                extract_modpack(f"/tmp/{file_name}")
                install_modpack()
            break

    if type == "mod":
        if input("another [y/n] -> ") in ["Y", "y", ""]:
            search_modrinth(type, version)

    exit()


def main():
    search_modrinth()


main()
