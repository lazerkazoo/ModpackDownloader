import json
from datetime import datetime
from os import listdir, makedirs, remove, rename
from os.path import abspath, basename, dirname, exists, expanduser
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
DOWNLOADS = f"{HOME}/Downloads"


session = requests.Session()


def download_file(url: str, dest: str):
    if not exists(dirname(dest)):
        makedirs(dirname(dest), exist_ok=True)
    with session.get(url, stream=True) as r:
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024 * 8):
                f.write(chunk)


def download_depends(file: str, version: str, pack: str):
    extract(file, "mod")

    data = load_json("/tmp/mod/fabric.mod.json")

    depends = data["depends"]
    if "minecraft" in depends:
        depends.pop("minecraft")
    if "fabricloader" in depends:
        depends.pop("fabricloader")
    if "fabric-api" in depends:
        depends.pop("fabric-api")
    if "java" in depends:
        depends.pop("java")

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
                download_file(file_url, f"{mods_dir}/{file_name}")


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
        main()
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


def install_fabric(mc: str, loader: str = ""):
    print("installing fabric...")
    download_file(
        "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.1.0/fabric-installer-1.1.0.jar",
        "/tmp/fabric-installer.jar",
    )

    cmd = [
        "java",
        "-jar",
        "/tmp/fabric-installer.jar",
        "client",
        "-mcversion",
        mc,
        "-noprofile",
    ]

    if loader != "":
        cmd.extend(["-loader", loader])

    run(cmd)


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


def update_modpack():
    pack = choose(get_modpacks(), "modpacks")
    mods_dir = f"{MC_DIR}/instances/{pack}/mods"
    pack_index = get_modrinth_index(f"{MC_DIR}/instances/{pack}/mrpack")
    mc_version = pack_index["dependencies"]["minecraft"]

    for file_entry in pack_index["files"]:
        if not file_entry["path"].startswith("mods/"):
            continue

        mod_url = file_entry["downloads"][0]
        project_id = mod_url.split("/data/")[1].split("/")[0]

        print(colored(f"Checking for updates for {file_entry['path']}...", "yellow"))

        versions_response = requests.get(
            f"https://api.modrinth.com/v2/project/{project_id}/version"
        )
        if not versions_response.ok:
            print(colored(f"Failed to fetch versions for {file_entry['path']}", "red"))
            continue

        versions = versions_response.json()

        latest_version = None
        for version in versions:
            if (
                mc_version in version["game_versions"]
                and "fabric" in version["loaders"]
            ):
                latest_version = version
                break

        if latest_version is None:
            print(
                colored(f"No compatible versions found for {file_entry['path']}", "red")
            )
            continue

        latest_sha1 = latest_version["files"][0]["hashes"]["sha1"]
        current_sha1 = file_entry["hashes"]["sha1"]

        if latest_sha1 == current_sha1:
            print(colored(f"{file_entry['path']} is already up-to-date.", "green"))
            continue

        print(colored(f"Updating {file_entry['path']}...", "yellow"))

        file_url = latest_version["files"][0]["url"]
        file_name = latest_version["files"][0]["filename"]
        target_path = f"{mods_dir}/{file_name}"

        download_file(file_url, target_path)

        old_mod_path = f"{mods_dir}/{basename(file_entry['path'])}"
        remove(old_mod_path)

        file_entry["path"] = f"mods/{file_name}"
        file_entry["hashes"] = latest_version["files"][0]["hashes"]
        file_entry["downloads"] = [file_url]
        file_entry["fileSize"] = latest_version["files"][0]["size"]

    save_json(f"{MC_DIR}/instances/{pack}/mrpack/modrinth.index.json", pack_index)

    print(colored(f"Update complete for {pack}!", "green"))


def download_modpack():
    file = choose(list(listdir(DOWNLOADS)), "modpacks downloaded")
    extract(f"{DOWNLOADS}/{file}", "modpack")

    install_modpack()


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
            f"{DOWNLOADS}/{pack}",  # where the zip will be created
            "zip",
            root_dir=f"{MC_DIR}/instances/{pack}/mrpack",
        )
        rename(f"{DOWNLOADS}/{pack}.zip", f"{DOWNLOADS}/{pack}.mrpack")


def remove_mod(pack=None):
    if pack is None:
        pack = choose(get_modpacks(), "modpack")
    pack_index = get_modrinth_index(f"{MC_DIR}/instances/{pack}/mrpack")
    mods_dir = f"{MC_DIR}/instances/{pack}/mods"
    mods = []

    for m in listdir(mods_dir):
        mods.append(m)

    mods.sort()
    for num, m in enumerate(mods):
        print(f"[{num + 1}] {m}")

    mod = input("choose [can enter name] -> ")

    try:
        mod = int(mod) - 1
        mod = mods[mod]
    except Exception:
        for i in mods:
            if i.lower().startswith(mod.lower()):
                mod = i
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

    launcher_data = load_json(profiles_file)

    profiles: dict = launcher_data["profiles"]

    profiles = launcher_data.get("profiles", {})

    for i in list(profiles.keys()):
        if profiles[i]["name"] == pack:
            profiles.pop(i)

    launcher_data["profiles"] = profiles

    save_json(profiles_file, launcher_data)

    for path in [
        f"{MC_DIR}/instances/{pack}",
        f"{MC_DIR}/versions/{pack}",
    ]:
        if exists(path):
            rmtree(path)


def search_modrinth(type=None, version=None, modpack=None):
    if exists("/tmp/mod"):
        rmtree("/tmp/mod")
    if exists("/tmp/modpack"):
        rmtree("/tmp/modpack")

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
    all_versions.sort()
    all_versions.reverse()

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
                index_file = get_modrinth_index(f"{MC_DIR}/instances/{modpack}/mrpack/")
                type_dir = f"{MC_DIR}/instances/{modpack}/{dirs[type]}"
                target = f"{type_dir}/{file_name}"

                makedirs(abspath(type_dir), exist_ok=True)

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

            extract_modpack(tmp_path, "modpack")
            install_modpack()
            return


def main():
    if exists("/tmp/modpack"):
        rmtree("/tmp/modpack")
    if exists("/tmp/mod"):
        rmtree("/tmp/mod")

    options = {
        "search modrinth": search_modrinth,
        "update modpack mods": update_modpack,
        "remove mod from modpack": remove_mod,
        "remove modpack": remove_modpack,
        "download modpack from file": download_modpack,
        "export modpack": export_modpack,
    }

    options[choose(list(options.keys()))]()


main()
