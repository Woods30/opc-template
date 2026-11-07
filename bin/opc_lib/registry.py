"""实例注册表：~/.config/opc/instances.json。"""

import json
import os
from datetime import datetime
from pathlib import Path

from . import paths


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load():
    path = paths.registry_path()
    if not path.is_file():
        return {"instances": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"instances": []}
    if not isinstance(data.get("instances"), list):
        data["instances"] = []
    return data


def save(data):
    path = paths.registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def upsert(instance_path, prefix, commit, upstream=""):
    instance_path = str(Path(instance_path).expanduser().resolve())
    data = load()
    now = _now()
    found = None
    for item in data["instances"]:
        if item.get("path") == instance_path:
            found = item
            break
    if found is None:
        found = {"path": instance_path, "installedAt": now}
        data["instances"].append(found)
    found["prefix"] = prefix
    found["updatedAt"] = now
    found["template"] = {"id": "opc-template", "commit": commit, "upstream": upstream}
    save(data)
    return found


def paths_list():
    return [Path(item["path"]) for item in load()["instances"] if item.get("path")]
