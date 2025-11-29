import json
from os import listdir, makedirs, remove, rename
from os.path import abspath, basename, exists
from shutil import copytree, make_archive, rmtree
from time import sleep, time

import requests
from termcolor import colored

from scripts.constants import DOWNLOADS, INST_DIR, MC_DIR
from scripts.helper import (
    choose,
    confirm,
    download_depends,
    download_file,
    extract,
    get_modpacks,
    get_modrinth_index,
    get_mrpack,
    install_modpack,
    load_json,
    remove_temps,
    save_json,
)


def change_modpack_ver():
    pack = choose(get_modpacks(), "modpack")
    version = input("choose version -> ")
    index_data = get_modrinth_index(get_mrpack(pack))

    index_data["dependencies"]["minecraft"] = version

    save_json(f"{get_mrpack(pack)}/modrinth.index.json", index_data)
    copytree(f"{get_mrpack(pack)}", "/tmp/modpack")
    rmtree(f"{MC_DIR}/versions/{index_data['name']}")
    rmtree(f"{INST_DIR}/{index_data['name']}")

    install_modpack()
    update_modpack(pack)


def custom_modpack():
    name = input("name -> ")
    version = input("minecraft version -> ")

    print(colored(f"gettings latest fabric version for mc {version}", "yellow"))
    url = f"https://meta.fabricmc.net/v2/versions/loader/{version}"
    response = requests.get(url)

    if response.status_code != 200:
        print(colored("error fetching Fabric data.", "red"))
        return

    data = response.json()

    if not data:
        print(colored("no Fabric loader found for that version.", "red"))
        return

    latest_loader = data[0]["loader"]["version"]

    index_data = {
        "formatVersion": 1,
        "game": "minecraft",
        "name": name,
        "versionId": "1.0",
        "files": [],
        "dependencies": {"fabric-loader": latest_loader, "minecraft": version},
    }
    makedirs("/tmp/modpack/overrides/config")
    save_json("/tmp/modpack/modrinth.index.json", index_data)

    install_modpack()


def update_modpack(pack=None):
    st = time()
    if pack is None:
        pack = choose(get_modpacks(), "modpacks")
    mods_dir = f"{INST_DIR}/{pack}/mods"
    pack_index = get_modrinth_index(get_mrpack(pack))
    mc_version = pack_index["dependencies"]["minecraft"]

    new_files = []
    for num, file_entry in enumerate(pack_index["files"]):
        new_files.append(file_entry)
        if not file_entry["path"].startswith("mods/"):
            continue

        mod_url = file_entry["downloads"][0]
        try:
            project_id = mod_url.split("/data/")[1].split("/")[0]
        except Exception:
            print(
                colored(
                    f"no compatible versions found for {file_entry['path']}, removing mod",
                    "red",
                )
            )
            new_files.remove(file_entry)
            continue

        print(
            colored(
                f"[{num + 1}/{len(pack_index['files'])}] checking for updates for {file_entry['path']}...",
                "cyan",
            )
        )

        versions_response = requests.get(
            f"https://api.modrinth.com/v2/project/{project_id}/version"
        )
        if not versions_response.ok:
            print(
                colored(
                    f"failed to fetch versions for {file_entry['path']}, removing mod",
                    "red",
                )
            )
            new_files.remove(file_entry)
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
                colored(
                    f"no compatible versions found for {file_entry['path']}, removing mod",
                    "red",
                )
            )
            new_files.remove(file_entry)
            continue

        latest_sha1 = latest_version["files"][0]["hashes"]["sha1"]
        current_sha1 = file_entry["hashes"]["sha1"]

        if latest_sha1 == current_sha1:
            continue

        print(colored(f"updating {file_entry['path']}...", "yellow"))

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

    pack_index["files"] = new_files
    save_json(f"{get_mrpack(pack)}/modrinth.index.json", pack_index)

    print(colored(f"update complete for {pack}", "green"))
    print(colored(f"updated in {round(time() - st, 2)}", "green"))


def download_modpack():
    file = choose(list(listdir(DOWNLOADS)), "modpacks downloaded")
    extract(f"{DOWNLOADS}/{file}", "modpack")

    install_modpack()


def export_modpack():
    pack = choose(get_modpacks(), "modpack")
    if confirm("copy resource/shader packs"):
        try:
            copytree(
                f"{INST_DIR}/{pack}/resourcepacks",
                f"{get_mrpack(pack)}/overrides",
                dirs_exist_ok=True,
            )
        except Exception:
            pass
        try:
            copytree(
                f"{INST_DIR}/{pack}/shaderpacks",
                f"{get_mrpack(pack)}/overrides",
                dirs_exist_ok=True,
            )
        except Exception:
            pass
        make_archive(
            f"{DOWNLOADS}/{pack}",  # where the zip will be created
            "zip",
            root_dir=f"{get_mrpack(pack)}",
        )
        rename(f"{DOWNLOADS}/{pack}.zip", f"{DOWNLOADS}/{pack}.mrpack")


def remove_mod(pack=None):
    if pack is None:
        pack = choose(get_modpacks(), "modpack")
    pack_index = get_modrinth_index(f"{get_mrpack(pack)}")
    mods_dir = f"{INST_DIR}/{pack}/mods"
    mods = []

    for m in listdir(mods_dir):
        mods.append(m)

    mods.sort()
    for num, m in enumerate(mods):
        print(f"[{num + 1}] {m}")

    mod = input("choose [can enter name] -> ")
    mod_ = mod

    try:
        mod = int(mod) - 1
        mod = mods[mod]
    except Exception:
        for i in mods:
            if i.lower().startswith(mod.lower()):
                mod = i
                break

    if mod == mod_:
        print(colored("could not find that mod, try again", "red"))
        sleep(0.5)
        remove_mod(pack)
        return

    if confirm(f"remove {mod}"):
        remove(f"{mods_dir}/{mod}")

        pack_index["files"] = [
            f
            for f in pack_index["files"]
            if not f["path"].lower().endswith(mod.lower())
        ]
        save_json(f"{get_mrpack(pack)}/modrinth.index.json", pack_index)

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
        f"{INST_DIR}/{pack}",
        f"{MC_DIR}/versions/{pack}",
    ]:
        if exists(path):
            rmtree(path)


def search_modrinth(type=None, version=None, modpack=None):
    remove_temps()
    if type is None:
        types = ["mod", "modpack", "resourcepack", "shader"]
        type = choose(types)

        if type != "modpack":
            modpack = choose(get_modpacks(), "modpack")
            index_file = f"{get_mrpack(modpack)}/modrinth.index.json"
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
                index_file = get_modrinth_index(f"{get_mrpack(modpack)}/")
                type_dir = f"{INST_DIR}/{modpack}/{dirs[type]}"
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
                    f"{get_mrpack(modpack)}/modrinth.index.json",
                    index_file,
                )

                if confirm("another"):
                    return search_modrinth(type, version, modpack)

            # MODPACK INSTALLATION
            tmp_path = f"/tmp/{file_name}"
            download_file(file_url, tmp_path)

            extract(tmp_path, "modpack")
            install_modpack()
            return


def main():
    remove_temps()
    if MC_DIR == "":
        print(colored("minecraft is not installed", "red"))
        exit()

    options = {
        "search modrinth": search_modrinth,
        "remove mod from modpack": remove_mod,
        "update modpack mods": update_modpack,
        "modpack": {
            "create custom modpack": custom_modpack,
            "download modpack from file": download_modpack,
            "change version of modpack": change_modpack_ver,
            "remove modpack": remove_modpack,
            "export modpack": export_modpack,
        },
    }

    choice = choose(list(options.keys()))
    if isinstance(options[choice], dict):
        options[choice][choose(list(options[choice].keys()))]()
    else:
        options[choice]()

    if confirm("do other stuff"):
        main()


main()
