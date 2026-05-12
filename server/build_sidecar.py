"""
Build the wanpi-server sidecar binary using PyInstaller.

Usage:
    python build_sidecar.py

Produces a single executable in dist/ named according to the current
platform's Tauri target triple, e.g.:
    wanpi-server-x86_64-pc-windows-msvc.exe   (Windows)
    wanpi-server-aarch64-apple-darwin          (macOS ARM)
    wanpi-server-x86_64-apple-darwin           (macOS Intel)
    wanpi-server-x86_64-unknown-linux-gnu      (Linux)
"""

import platform
import subprocess
import shutil
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent
PROJECT_ROOT = SERVER_DIR.parent
TAURI_BIN_DIR = PROJECT_ROOT / "src-tauri" / "binaries"


def get_target_triple() -> str:
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "windows":
        arch = "x86_64" if machine in ("amd64", "x86_64") else "aarch64"
        return f"{arch}-pc-windows-msvc"
    elif system == "darwin":
        arch = "aarch64" if machine == "arm64" else "x86_64"
        return f"{arch}-apple-darwin"
    else:
        arch = "x86_64" if machine in ("amd64", "x86_64") else machine
        return f"{arch}-unknown-linux-gnu"


def build():
    triple = get_target_triple()
    ext = ".exe" if platform.system().lower() == "windows" else ""
    output_name = f"wanpi-server{ext}"
    final_name = f"wanpi-server-{triple}{ext}"

    static_dir = SERVER_DIR / "static"
    if not static_dir.exists():
        print("[WARNING] static/ directory not found. Build frontend first.")
        print("  cd react-ui && npm run build && cp -r dist/ ../server/static/")

    sep = ";" if platform.system().lower() == "windows" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "wanpi-server",
        "--noconfirm",
        "--clean",
        "--log-level", "WARN",
    ]

    if static_dir.exists():
        cmd += ["--add-data", f"static{sep}static"]

    hidden_imports = [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "multipart",
        "bcrypt",
        "jwt",
        "httpx",
        "fal_client",
        "openai",
        "google.genai",
        "gtts",
        "mutagen",
        "aiofiles",
    ]
    for hi in hidden_imports:
        cmd += ["--hidden-import", hi]

    cmd.append("main.py")

    print(f"[BUILD] Target triple: {triple}")
    print(f"[BUILD] Running PyInstaller...")
    subprocess.run(cmd, cwd=str(SERVER_DIR), check=True)

    dist_file = SERVER_DIR / "dist" / output_name
    if not dist_file.exists():
        print(f"[ERROR] Expected output not found: {dist_file}")
        sys.exit(1)

    TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = TAURI_BIN_DIR / final_name
    shutil.copy2(str(dist_file), str(dest))
    print(f"[BUILD] Copied to {dest}")
    print(f"[BUILD] Done! Sidecar binary: {final_name}")
    return str(dest)


if __name__ == "__main__":
    build()
