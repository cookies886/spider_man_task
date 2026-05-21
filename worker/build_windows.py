"""Build a standalone Windows executable for the SpiderMan worker.

Run this on a **Windows** machine (PyInstaller produces a binary native to the
platform it runs on; cross-compilation isn't supported).

Prerequisites:
    python -m venv .venv
    .venv\\Scripts\\activate
    pip install -e .
    pip install pyinstaller

Then:
    python build_windows.py

Output:
    dist/windows_worker.exe          # standalone .exe
    dist_release/windows_worker_1.0/ # bundle with .exe + .env.example + README
    dist_release/windows_worker_1.0.zip
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "1.0"

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "dist_release" / f"windows_worker_{VERSION}"


def run_pyinstaller():
    """Compile agent/main.py to dist/windows_worker.exe."""
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=windows_worker",
        "--onefile",
        "--console",
        "--clean",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
        # psutil and websockets need their data files; PyInstaller usually finds
        # them, but be explicit just in case.
        "--collect-submodules=websockets",
        "--collect-submodules=psutil",
        str(ROOT / "agent" / "main.py"),
    ]
    print("[BUILD] " + " ".join(args))
    subprocess.run(args, check=True)


def stage_release():
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir(parents=True)

    src_exe = ROOT / "dist" / "windows_worker.exe"
    if not src_exe.exists():
        sys.exit(f"[ERR] expected {src_exe} not found — pyinstaller failed?")
    shutil.copy2(src_exe, RELEASE / "windows_worker.exe")

    (RELEASE / ".env.example").write_text(_ENV_EXAMPLE, encoding="utf-8")
    (RELEASE / "README.txt").write_text(_README, encoding="utf-8")
    (RELEASE / "start.bat").write_text(_START_BAT, encoding="utf-8")

    out_zip = ROOT / "dist_release" / f"windows_worker_{VERSION}.zip"
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in RELEASE.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(RELEASE.parent))
    print(f"[OK] release zip: {out_zip}")


_ENV_EXAMPLE = """\
# SpiderMan Windows Worker 配置
# ----------------------------------------------------
# 1. 在主控 Web UI 添加节点，复制显示出来的 API Key
# 2. 把下面三个值填好
# 3. 复制本文件为 .env，然后双击 start.bat（或 windows_worker.exe）

MASTER_URL=ws://主控IP:8000
API_KEY=填入主控显示的-api-key
NODE_ID=填入-node-id
NODE_NAME=windows-prod-1

# 工作目录（任意可写路径）
WORK_DIR=C:\\spiderman-worker

LISTEN_PORT=8001
HEARTBEAT_INTERVAL=5
"""

_README = """\
SpiderMan Windows Worker 使用说明
=================================

1. 在主控（master）UI 添加一行节点，记下显示出来的 API Key
2. 复制本目录的 .env.example 为 .env
3. 用记事本打开 .env，填好 MASTER_URL、API_KEY、NODE_ID
4. 双击 start.bat 启动（会读 .env 然后跑 windows_worker.exe）
   或者直接双击 windows_worker.exe（也能跑，但需要把变量先 set 进环境）

确认 worker 状态：
- 主控 UI「Worker 节点」页面会看到本机变成 online
- 创建任务时选「指定节点」并填 NODE_ID 即可派发到本机

排错：
- 黑窗口立刻消失 → 命令行运行 start.bat 看错误
- "connection lost"反复打印 → 检查能否 ping 通主控、API_KEY 是否和主控记录的一致
- Windows 防火墙可能拦截出站 ws 连接，必要时放行
"""

_START_BAT = """\
@echo off
chcp 65001 >NUL
cd /d "%~dp0"
if not exist .env (
    echo [ERR] .env 不存在。请先 copy .env.example .env 并填好。
    pause
    exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
)
echo [INFO] starting windows_worker.exe with NODE_ID=%NODE_ID%
windows_worker.exe
pause
"""


if __name__ == "__main__":
    print(f"[BUILD] SpiderMan Windows worker v{VERSION}")
    print(f"[BUILD] python: {sys.version}")
    if os.name != "nt":
        print(
            "[WARN] 你不在 Windows 上跑这个脚本！PyInstaller 不能交叉编译，"
            "产出的 .exe 在 Windows 上不能跑。"
        )
        if "--force" not in sys.argv:
            sys.exit("如果你确认要继续，请加 --force 参数")
    run_pyinstaller()
    stage_release()
    print(f"[DONE] 产物在 {RELEASE.parent}")
