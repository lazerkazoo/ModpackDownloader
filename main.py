import json
from datetime import datetime
from os import listdir, makedirs, rename
from os.path import expanduser
from shutil import copy, copytree
from subprocess import run
from time import time
from uuid import uuid4
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


def get_modpacks():
    return listdir(f"{MC_DIR}/instances")


def choose_modpack():
    packs = get_modpacks()
    for num, i in enumerate(packs):
        print(f"[{num + 1}] {i}")

    return packs[int(input("choose -> ")) - 1]


def get_modrinth_index(file="/tmp/modpack/"):
    with open(f"{file}/modrinth.index.json", "r") as f:
        return json.load(f)


def install_fabric(mc: str, loader: str):
    print("installing fabric...")
    download_file(
        "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.1.0/fabric-installer-1.1.0.jar",
        "/tmp/fabric-installer.jar",
    )
    run(
        [
            "java",
            "-jar",
            "/tmp/fabric-installer.jar",
            "client",
            "-mcversion",
            mc,
            "-loader",
            loader,
            "-downloadMinecraft",
            "-noprofile",
        ]
    )


def install_modpack():
    st = time()
    data = get_modrinth_index()
    depends = data["dependencies"]
    name = data["name"]
    files = data["files"]
    dir = f"{MC_DIR}/instances/{name}"
    copytree(
        "/tmp/modpack/overrides/", f"{MC_DIR}/instances/{name}/", dirs_exist_ok=True
    )
    makedirs(f"{dir}/mods", exist_ok=True)

    install_fabric(depends["minecraft"], depends["fabric-loader"])
    copytree(
        f"{MC_DIR}/versions/fabric-loader-{depends['fabric-loader']}-{depends['minecraft']}",
        f"{MC_DIR}/versions/{name}",
        dirs_exist_ok=True,
    )
    rename(
        f"{MC_DIR}/versions/{name}/fabric-loader-{depends['fabric-loader']}-{depends['minecraft']}.json",
        f"{MC_DIR}/versions/{name}/{name}.json",
    )

    copy(
        f"{MC_DIR}/libraries/net/fabricmc/intermediary/{depends['minecraft']}/intermediary-{depends['minecraft']}.jar",
        f"{MC_DIR}/versions/{name}/{name}.jar",
    )

    # Update the JSON to have correct id
    with open(f"{MC_DIR}/versions/{name}/{name}.json", "r") as f:
        version_data = json.load(f)
    version_data["id"] = name
    with open(f"{MC_DIR}/versions/{name}/{name}.json", "w") as f:
        json.dump(version_data, f, indent=2)

    downloads = {i["downloads"][0]: f"{dir}/{i['path']}" for i in files}

    for num, url in enumerate(downloads):
        if url.endswith(".jar"):
            print(f"[{num + 1}/{len(downloads)}] downloading {url.split('/')[-1]}")
            download_file(url, downloads[url])

    print(f"\ndownloaded mods in {round(time() - st, 2)}s!")

    with open(f"{MC_DIR}/launcher_profiles.json", "r") as f:
        launcher_data = json.load(f)

    profiles = launcher_data.setdefault("profiles", {})

    profile_id = uuid4().hex  # UUID as json-safe string
    timestamp = datetime.utcnow().isoformat() + "Z"

    profiles[profile_id] = {
        "created": timestamp,
        "lastUsed": timestamp,
        "icon": "Grass",
        "name": name,
        "type": "custom",
        "lastVersionId": name,
        "gameDir": f"{MC_DIR}/instances/{name}",
    }

    with open(f"{MC_DIR}/launcher_profiles.json", "w") as f:
        json.dump(launcher_data, f, indent=2)

    print(f"Created launcher profile '{name}' ({profile_id})")
    copytree("/tmp/modpack", f"{dir}/mrpack", dirs_exist_ok=True)


def search_modrinth(type=None, version=None, modpack=None):
    if type is None:
        types = ["mod", "modpack"]
        for num, t in enumerate(types):
            print(f"[{num + 1}] {t}")
        try:
            type = types[int(input("choose -> ")) - 1]
            if type == "mod":
                modpack = choose_modpack()
                file = json.load(
                    open(f"{MC_DIR}/instances/{modpack}/mrpack/modrinth.index.json")
                )
                version = file["dependencies"]["minecraft"]
        except (EOFError, ValueError, KeyboardInterrupt):
            print("No input provided. Exiting.")
            return
    if version is None:
        try:
            version = input("mc version -> ")
        except (EOFError, KeyboardInterrupt):
            print("No input provided. Exiting.")
            return
    try:
        query = input("search modrinth -> ")
    except (EOFError, KeyboardInterrupt):
        print("No input provided. Exiting.")
        return
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
        print(f"[{num + 1}] {hit['title']}")

    try:
        choice = int(input("choose -> ")) - 1
    except (EOFError, ValueError, KeyboardInterrupt):
        print("No input provided. Exiting.")
        return

    project_id = hits[choice]["project_id"]

    versions = requests.get(
        f"https://api.modrinth.com/v2/project/{project_id}/version"
    ).json()

    for v in versions:
        if "fabric" in v["loaders"] and version in v["game_versions"]:
            file_url = v["files"][0]["url"]
            file_name = v["files"][0]["filename"]
            dir = f"/tmp/{file_name}"
            if type == "mod":
                dir = f"{MC_DIR}/instances/{modpack}/mods/{file_name}"
            download_file(file_url, dir)
            if type == "modpack":
                extract_modpack(f"/tmp/{file_name}")
                install_modpack()
            break

    if type == "mod":
        try:
            if input("another [y/n] -> ") in ["Y", "y", ""]:
                search_modrinth(type, version, modpack)
        except (EOFError, KeyboardInterrupt):
            print("No input provided. Exiting.")
            return

    exit()


def main():
    search_modrinth()


main()
