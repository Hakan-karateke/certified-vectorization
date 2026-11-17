"""Her masaüstü kabul testini kendi Python/Tk sürecinde gerçek olay döngüsüyle çalıştırır."""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


def pytest_pyfunc_call(pyfuncitem):
    """Windows Tcl'nin ardışık kök başlatma durumunu testler arasında paylaşmaz.

    Gerçek uygulama tek Tk kökü kullanır. Çocuk pytest sonucu XML'den okunur;
    alt süreçte atlanan test üst süreçte geçti olarak raporlanmaz.
    """
    if "gui" not in pyfuncitem.module.__name__ or os.environ.get("SD_GUI_TEST_SUBPROCESS"):
        return None
    directory = pyfuncitem.funcargs["tmp_path"] / "isolated-gui"
    directory.mkdir()
    report = directory / "junit.xml"
    env = os.environ.copy()
    env["SD_GUI_TEST_SUBPROCESS"] = "1"
    command = [
        sys.executable,
        "-m",
        "pytest",
        pyfuncitem.nodeid,
        "-q",
        "-rs",
        "--basetemp",
        str(directory / "tmp"),
        "--junitxml",
        str(report),
    ]
    result = subprocess.run(command, env=env, capture_output=True, timeout=180)
    output = (result.stdout + result.stderr).decode("utf8", errors="replace")
    (directory / "pytest.log").write_text(output, encoding="utf8")
    assert result.returncode == 0, output
    tree = ET.parse(report)
    skipped = tree.find(".//skipped")
    if skipped is not None:
        pytest.skip(skipped.get("message", "Alt süreçte ekran kullanılamadı."))
    assert len(tree.findall(".//testcase")) == 1, output
    return True
