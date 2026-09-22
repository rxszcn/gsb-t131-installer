"""
轮子文件名的解析与两处名字比对各说各话

跑法：PYTHONPATH=src .venv/bin/python repro/wheel-filename-parse.py
"""

import os
import stat
import subprocess
import sys
import tempfile
import zipfile
from base64 import urlsafe_b64encode
from hashlib import sha256
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import installer  # noqa: E402

print("code under test:", installer.__file__)

from installer.destinations import SchemeDictionaryDestination  # noqa: E402
from installer.records import RecordEntry  # noqa: E402
from installer.scripts import Script  # noqa: E402
from installer.sources import WheelFile  # noqa: E402
from installer.utils import parse_wheel_filename  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="bnd-"))
SCHEMES = ("purelib", "platlib", "headers", "scripts", "data")


def rec_lines(files, extra=(), skip=()):
    out = []
    for name, content in files.items():
        if name in skip:
            continue
        data = content if isinstance(content, bytes) else content.encode()
        h = urlsafe_b64encode(sha256(data).digest()).decode().rstrip("=")
        out.append(f"{name},sha256={h},{len(data)}")
    out.extend(extra)
    return out


def build(name, files, record=None, record_path=None):
    """Write a wheel; `record` overrides the RECORD content entirely."""
    path = TMP / name
    with zipfile.ZipFile(path, "w") as archive:
        for fname, content in files.items():
            data = content if isinstance(content, bytes) else content.encode()
            info = zipfile.ZipInfo(fname)
            mode = 0o755 if "/bin/" in fname or fname.endswith(".sh") else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data)
        if record is not None:
            archive.writestr(record_path, record)
    return str(path)


def install(whl, tag="", interpreter=sys.executable, kind="posix"):
    root = TMP / f"out-{tag or Path(whl).stem}"
    root.mkdir(parents=True, exist_ok=True)
    scheme_dict = {}
    for s in SCHEMES:
        d = root / s
        d.mkdir(parents=True, exist_ok=True)
        scheme_dict[s] = str(d)
    dest = SchemeDictionaryDestination(scheme_dict, interpreter, kind)
    with WheelFile.open(whl) as source:
        installer.install(source, dest, {})
    return root, sorted(
        str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
    )


def run(path):
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    try:
        res = subprocess.run([str(path)], capture_output=True, text=True, timeout=20)
        return f"rc={res.returncode} out={res.stdout.strip()!r} err={res.stderr.strip()!r}"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


WHEEL = "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"


def meta(dist, di, version="1.0.0"):
    return {
        f"{di}/WHEEL": WHEEL,
        f"{di}/METADATA": f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n",
    }


# --------------------------------------------------------- 5: filename parse
def b5():
    names = [
        "my-pkg-1.0-py3-none-any.whl",
        "my-pkg-1.0.0-py3-none-any.whl",
        "some-very-long-package-1.0-cp312-cp312-manylinux_2_17_x86_64.whl",
        "foo-1.0-123abc-py3-none-any.whl",
        "foo-1.0-0-py3-none-any.whl",
        "foo-1.0-07-py3-none-any.whl",
        "foo-1.0-py3-none-any-docs.whl",
        "foo-1.0.0-1-py3-none-any.whl",
        "my_pkg-1.0.0-py3-none-any.whl",
    ]
    for n in names:
        try:
            ours = repr(parse_wheel_filename(n))
        except Exception as exc:
            ours = f"{type(exc).__name__}: {exc}"
        try:
            import packaging.utils

            ref = repr(packaging.utils.parse_wheel_filename(n))[:120]
        except Exception as exc:
            ref = f"{type(exc).__name__}: {exc}"
        print(f"[5] {n}\n      installer -> {ours}\n      packaging -> {ref}")
    print("[5] WheelFilename fields:", parse_wheel_filename.__module__,
          installer.utils.WheelFilename._fields,
          "| has to_string:", hasattr(installer.utils.WheelFilename, "to_string"))

    # downstream symptom: a wheel named with a hyphen, dist-info spelled with _
    di = "my_pkg-1.0.dist-info"
    files = {
        "my_pkg/__init__.py": "x = 1\n",
        **meta("my_pkg", di, version="1.0"),
    }
    files[f"{di}/RECORD"] = "\n".join(
        rec_lines(files, skip=(f"{di}/RECORD",)) + [f"{di}/RECORD,,"]
    ) + "\n"
    whl = build("my-pkg-1.0-py3-none-any.whl", files)
    try:
        with WheelFile.open(whl) as source:
            print("[5] WheelFile(dashed name) distribution/version:",
                  source.distribution, source.version, source.dist_info_dir)
    except Exception as exc:
        print(f"[5] WheelFile(dashed name) -> {type(exc).__name__}: {exc}")



b5()
