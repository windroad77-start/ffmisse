import importlib.util
import os
import subprocess
import sys

from plugin import *


REQUIRED_PACKAGES = [
    ("cloudscraper", "cloudscraper"),
    ("beautifulsoup4", "bs4"),
    ("lxml", "lxml"),
    ("PySocks", "socks"),
]


def _ensure_requirements():
    missing = [
        package
        for package, module_name in REQUIRED_PACKAGES
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing:
        return
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    except Exception as e:
        print(f"Failed to install requirements: {e}")


def _get_runtime_package_name():
    return os.path.basename(os.path.dirname(__file__))


runtime_package_name = _get_runtime_package_name()

_ensure_requirements()

setting = {
    "filepath": __file__,
    "use_db": True,
    "use_default_setting": True,
    "home_module": "main",
    "menu": {
        "uri": runtime_package_name,
        "name": "MissKon",
        "list": [
            {"uri": "main", "name": "최신"},
            {"uri": "top3", "name": "인기 (3일)"},
            {"uri": "top7", "name": "인기 (7일)"},
            {"uri": "top30", "name": "인기 (30일)"},
            {"uri": "top60", "name": "인기 (60일)"},
            {"uri": "search", "name": "검색"},
            {"uri": "setting", "name": "설정"},
            {"uri": "log", "name": "로그"},
        ],
    },
    "default_route": "single",
}

P = create_plugin_instance(setting)

try:
    from .mod_main import ModuleMain

    P.set_module_list([ModuleMain])
except Exception as e:
    P.logger.error(f"Exception:{str(e)}")
