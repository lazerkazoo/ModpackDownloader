import json
import re
from datetime import datetime
from os import listdir, makedirs, remove, rename
from os.path import abspath, dirname, exists, expanduser
from shutil import copy, copytree, make_archive, rmtree
from subprocess import run
from sys import exit
from time import time
from uuid import uuid4
from zipfile import ZipFile

import requests
from termcolor import colored

HOME = expanduser("~")
MC_DIR = f"{HOME}/.minecraft"


session = requests.Session()


def remove_old_versions(mods_dir: str, new_filename: str):
    base = re.split(r"[-_]?\d", new_filename, maxsplit=1)[0]

    for file in listdir(mods_dir):
        if file == new_filename:
            continue

        if file.startswith(base):
            print(colored(f"Removing old version: {file}", "red"))
            remove(f"{mods_dir}/{file}")


def download_file(url: str, dest: str, session=session):
    if not exists(dirname(dest)):
        makedirs(dirname(dest), exist_ok=True)
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024 * 8):
                f.write(chunk)


def download_depends(file: str, version: str, pack: str):
    with ZipFile(file, "r") as z:
        z.extractall("/tmp/mod")

    with open("/tmp/mod/fabric.mod.json", "r") as f:
        data = json.load(f)

    depends = data["depends"]

    if len(depends) <= 0:
        return
    print(colored("downloading dependencies...", "yellow"))

    for dep in depends:
        params = {
            "query": dep,
            "facets": f'[["project_type:mod"], ["categories:fabric"], ["versions:{version}"]]',
        }
        response = requests.get("https://api.modrinth.com/v2/search", params=params)
        r_data = response.json()
        hits = r_data["hits"]
        project_id = hits[0]["project_id"]
        versions = requests.get(
            f"https://api.modrinth.com/v2/project/{project_id}/version"
        ).json()
        for v in versions:
            if version in v["game_versions"] and "fabric" in v["loaders"]:
                file_url = v["files"][0]["url"]
                file_name = v["files"][0]["filename"]
                mods_dir = f"{MC_DIR}/instances/{pack}/mods"
                remove_old_versions(mods_dir, file_name)
                download_file(file_url, f"{mods_dir}/{file_name}")


def extract_modpack(file):
    with ZipFile(file, "r") as z:
        z.extractall("/tmp/modpack")


def get_modpacks():
    return listdir(f"{MC_DIR}/instances")


def confirm(txt: str):
    return input(f"{txt} [y/n] -> ") in ["Y", "y", ""]


def choose(lst: list, stuff: str = "stuff"):
    if len(lst) <= 0:
        print(colored(f"no {stuff}s installed!", "yellow"))
        main()
    for num, i in enumerate(lst):
        print(f"[{num + 1}] {i}")

    return lst[int(input("choose -> ")) - 1]


def save_json(file: str, js):
    with open(file, "w") as f:
        json.dump(js, f, indent=2)


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

    print(colored(f"downloaded mods in {round(time() - st, 2)}s!", "green"))

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


def export_modpack():
    pack = choose(get_modpacks(), "modpack")
    if confirm("copy resource/shader packs"):
        try:
            copytree(
                f"{MC_DIR}/instances/{pack}/resourcepacks",
                f"{MC_DIR}/instances/{pack}/mrpack/overrides",
                dirs_exist_ok=True,
            )
        except Exception:
            pass
        try:
            copytree(
                f"{MC_DIR}/instances/{pack}/shaderpacks",
                f"{MC_DIR}/instances/{pack}/mrpack/overrides",
                dirs_exist_ok=True,
            )
        except Exception:
            pass
        make_archive(
            f"{HOME}/Downloads/{pack}",  # where the zip will be created
            "zip",
            root_dir=f"{MC_DIR}/instances/{pack}/mrpack",
        )
        rename(f"{HOME}/Downloads/{pack}.zip", f"{HOME}/Downloads/{pack}.mrpack")


def remove_mod(pack=None):
    if pack is None:
        pack = choose(get_modpacks(), "modpack")
    pack_index = get_modrinth_index(f"{MC_DIR}/instances/{pack}/mrpack")
    mods_dir = f"{MC_DIR}/instances/{pack}/mods"
    mods = []

    for num, m in enumerate(listdir(mods_dir)):
        print(f"[{num + 1}] {m}")
        mods.append(m)

    mods.sort()
    mod = input("choose [can enter name] -> ")

    try:
        mod = int(mod) - 1
        mod = mods[mod]
    except Exception:
        for i in mods:
            mod = i
            if i.lower().startswith(mod.lower()):
                break

    if confirm(f"remove {mod}"):
        remove(f"{mods_dir}/{mod}")

        pack_index["files"] = [
            f
            for f in pack_index["files"]
            if not f["path"].lower().endswith(mod.lower())
        ]
        save_json(f"{MC_DIR}/instances/{pack}/mrpack/modrinth.index.json", pack_index)

    if confirm("another"):
        remove_mod(pack)


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
            index_file = f"{MC_DIR}/instances/{modpack}/mrpack/modrinth.index.json"
            version = json.load(open(index_file))["dependencies"]["minecraft"]

    if version is None:
        version = input("mc version [just press enter to search all versions] -> ")

    query = input("search modrinth -> ")

    base_facets = [[f"project_type:{type}"]]

    if type not in ["resourcepack", "shader"]:
        base_facets.append(["categories:fabric"])

    if version not in ("", None) and type not in ["resourcepack", "shader"]:
        base_facets.append([f"versions:{version}"])

    params = {"query": query, "facets": json.dumps(base_facets)}

    response = requests.get("https://api.modrinth.com/v2/search", params=params)
    hits = response.json().get("hits", [])

    if not hits:
        print(colored(f"no {type}s found", "red"))
        return search_modrinth(type, version)

    for num, hit in enumerate(hits):
        print(f"[{num + 1}] {hit['title']}")

    choice = hits[int(input("choose -> ")) - 1]
    project_id = choice["project_id"]

    versions = requests.get(
        f"https://api.modrinth.com/v2/project/{project_id}/version"
    ).json()

    all_versions = list({v["game_versions"][0] for v in versions})

    if version == "":
        version = choose(list(reversed(all_versions)), "version")

    for v in versions:
        if version in v["game_versions"] and "fabric" in v["loaders"]:
            file_info = v["files"][0]
            file_url = file_info["url"]
            file_name = file_info["filename"]
            dirs = {
                "mod": "mods",
                "resourcepack": "resourcepacks",
                "shader": "shaderpacks",
            }

            if type != "modpack":
                index_file = get_modrinth_index(abspath(dirname(index_file)))
                type_dir = f"{MC_DIR}/instances/{modpack}/{dirs[type]}"
                target = f"{type_dir}/{file_name}"

                makedirs(abspath(type_dir), exist_ok=True)
                remove_old_versions(type_dir, file_name)

                print(colored(f"downloading {file_name}...", "yellow"))
                download_file(file_url, target)

                download_depends(target, version, modpack)
                new_entry = {
                    "path": f"{dirs[type]}/{file_name}",
                    "hashes": {
                        "sha1": v["files"][0]["hashes"]["sha1"],
                        "sha512": v["files"][0]["hashes"].get("sha512", ""),
                    },
                    "downloads": [file_url],
                    "fileSize": v["files"][0]["size"],
                }
                index_file["files"] = [
                    f
                    for f in index_file["files"]
                    if f["path"].lower() != new_entry["path"].lower()
                ]

                index_file["files"].append(new_entry)

                save_json(
                    f"{MC_DIR}/instances/{modpack}/mrpack/modrinth.index.json",
                    index_file,
                )

                if confirm("another"):
                    return search_modrinth(type, version, modpack)
                exit()

            # MODPACK INSTALLATION
            tmp_path = f"/tmp/{file_name}"
            download_file(file_url, tmp_path)

            extract_modpack(tmp_path)
            install_modpack()
            return


def main():
    options = {
        "search modrinth": search_modrinth,
        "remove modpack": remove_modpack,
        "remove mod from modpack": remove_mod,
        "export modpack": export_modpack,
    }

    options[choose(list(options.keys()))]()


main()
