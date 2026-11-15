"""将语料原件、运行结果和导入状态原子写入本地目录。"""

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile


def read_json(path, default=None):
    """读取 JSON。文件缺失时返回调用方提供的初始值。"""
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_bytes(path, content):
    """完成写入后替换目标文件，使中断的写入不会留下半份记录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
        temp = Path(stream.name)
        stream.write(content)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def write_json(path, value):
    """原子持久化可供人工查阅的 UTF-8 JSON。"""
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def store_file(root, content, fmt):
    """按内容摘要保存原件并返回相对路径与完整性信息。"""
    digest = hashlib.sha256(content).hexdigest()
    path = Path("artifacts") / f"{digest}.{fmt}"
    if not (root / path).exists():
        write_bytes(root / path, content)
    return {"path": path.as_posix(), "sha256": digest, "format": fmt}
