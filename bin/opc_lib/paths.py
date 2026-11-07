"""路径口径：所有全局位置只在这里出现，测试用环境变量整体重定向。"""

import os
from pathlib import Path


def home():
    return Path(os.environ.get("HOME") or Path.home())


def _xdg_config():
    return Path(os.environ.get("XDG_CONFIG_HOME") or (home() / ".config"))


def _xdg_data():
    return Path(os.environ.get("XDG_DATA_HOME") or (home() / ".local" / "share"))


def config_dir():
    return Path(os.environ.get("OPC_CONFIG_DIR") or (_xdg_config() / "opc"))


def data_dir():
    return Path(os.environ.get("OPC_DATA_DIR") or (_xdg_data() / "opc"))


def cache_dir():
    return Path(os.environ.get("OPC_CACHE_DIR") or (data_dir() / "template"))


def bin_dir():
    return Path(os.environ.get("OPC_BIN_DIR") or (home() / ".local" / "bin"))


def herdr_app_home():
    return Path(os.environ.get("HERDR_APP_HOME") or (_xdg_config() / "herdr-app"))


def herdr_core_home():
    return Path(os.environ.get("HERDR_CORE_HOME") or (_xdg_config() / "herdr-core"))


def registry_path():
    return config_dir() / "instances.json"


def ui_state_path():
    return config_dir() / "ui.json"


def backup_root():
    return config_dir() / "backups"


def repo_root_from_script():
    """bin/opc_lib/paths.py -> 仓库根。"""
    return Path(__file__).resolve().parents[2]


def as_path(value):
    return Path(value).expanduser().resolve()


def is_within(child, parent):
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
