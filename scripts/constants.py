from os.path import exists, expanduser

HOME = expanduser("~")
MC_DIR = (
    f"{HOME}/.minecraft"
    if exists(f"{HOME}/.minecraft")
    else f"{HOME}/.var/app/com.mojang.Minecraft/.minecraft"
    if exists(f"{HOME}.var/app/com.mojang.Minecraft/.minecraft")
    else ""
)
INST_DIR = f"{MC_DIR}/instances"
DOWNLOADS = f"{HOME}/Downloads"
