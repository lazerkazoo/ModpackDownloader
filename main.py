import json
from datetime import datetime
from os import listdir, makedirs, remove, rename
from os.path import abspath, dirname, exists, expanduser
from shutil import copy, copytree, rmtree
from subprocess import run
from time import time
from uuid import uuid4
from zipfile import ZipFile

import requests
from termcolor import colored

MC_DIR = f"{expanduser('~')}/.minecraft"


session = requests.Session()


def download_file(url: str, dest: str, session=session):
    if not exists(dirname(dest)):
        makedirs(dirname(dest), exist_ok=True)
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


def choose(lst: list, stuff: str = "stuff"):
    if len(lst) <= 0:
        print(colored(f"no {stuff}s installed!", "yellow"))
        main()
    for num, i in enumerate(lst):
        print(f"[{num + 1}] {i}")

    return lst[int(input("choose -> ")) - 1]


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
        print(
            colored(
                f"[{num + 1}/{len(downloads)}] downloading {url.split('/')[-1]}",
                "yellow",
            )
        )
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


def remove_mod():
    pack = choose(get_modpacks(), "modpack")
    mods_dir = f"{MC_DIR}/instances/{pack}/mods"
    mods = []
    for m in listdir(mods_dir):
        mods.append(m)

    remove(f"{mods_dir}/{choose(mods)}")


def remove_modpack():
    pack = choose(get_modpacks(), "modpack")
    profiles_file = f"{MC_DIR}/launcher_profiles.json"

    with open(profiles_file, "r") as f:
        profiles: dict = json.load(f)["profiles"]

    with open(profiles_file, "r") as f:
        launcher_data = json.load(f)

    profiles = launcher_data.get("profiles", {})

    for i in list(profiles.keys()):
        if profiles[i]["name"] == pack:
            profiles.pop(i)

    launcher_data["profiles"] = profiles

    with open(profiles_file, "w") as f:
        json.dump(launcher_data, f, indent=2)

    for path in [
        f"{MC_DIR}/instances/{pack}",
        f"{MC_DIR}/versions/{pack}",
    ]:
        if exists(path):
            rmtree(path)


def search_modrinth(type=None, version=None, modpack=None):
    if type is None:
        types = ["mod", "modpack", "resourcepack", "shader"]
        type = choose(types)
        if type != "modpack":
            modpack = choose(get_modpacks(), "modpack")
            file = json.load(
                open(f"{MC_DIR}/instances/{modpack}/mrpack/modrinth.index.json")
            )
            version = file["dependencies"]["minecraft"]

    if version is None:
        try:
            version = input("mc version [just press enter to search all versions] -> ")
        except (EOFError, KeyboardInterrupt):
            print(colored("no input provided, restarting"))
            main()
    query = input("search modrinth -> ")
    if version == "":
        params = {
            "query": query,
            "facets": f'[["project_type:{type}"], ["categories:fabric"]]',
        }
    elif type in ["resourcepack", "shader"]:
        params = {
            "query": query,
            "facets": f'[["project_type:{type}"]]',
        }
    else:
        params = {
            "query": query,
            "facets": f'[["project_type:{type}"], ["categories:fabric"], ["versions:{version}"]]',
        }

    response = requests.get("https://api.modrinth.com/v2/search", params=params)
    r_data = response.json()
    hits = r_data["hits"]
    if len(hits) <= 0:
        print(colored(f"no {type}s found", "red"))
        search_modrinth(type, version)

    choice = choose(hits, type)

    project_id = hits[choice]["project_id"]

    versions = requests.get(
        f"https://api.modrinth.com/v2/project/{project_id}/version"
    ).json()
    vers = []
    for v in versions:
        if v["game_versions"][0] not in vers:
            vers.append(v["game_versions"][0])

    for v in versions:
        if version == "":
            version = choose(list(reversed(vers)), "version")
        if "fabric" in v["loaders"] and version in v["game_versions"]:
            dirs = {
                "mod": "mods",
                "resourcepack": "resourcepacks",
                "shader": "shaderpacks",
            }
            file_url = v["files"][0]["url"]
            file_name = v["files"][0]["filename"]
            dir = f"/tmp/{file_name}"
            if type != "modpack":
                dir = f"{MC_DIR}/instances/{modpack}/{dirs[type]}/{file_name}"
                makedirs(abspath(dirname(dir)), exist_ok=True)
                download_file(file_url, dir)
                try:
                    if input("another [y/n] -> ") in ["Y", "y", ""]:
                        search_modrinth(type, version, modpack)
                    exit()
                except (EOFError, KeyboardInterrupt):
                    print(colored("no input provided, restarting"))
                    main()
            download_file(file_url, dir)
            if type == "modpack":
                extract_modpack(f"/tmp/{file_name}")
                install_modpack()
            break


def main():
    options = {
        "search modrinth": search_modrinth,
        "remove modpack": remove_modpack,
        "remove mod from pack": remove_mod,
    }

    options[choose(list(options.keys()))]()


main()
