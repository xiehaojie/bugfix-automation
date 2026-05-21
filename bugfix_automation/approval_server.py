from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import urllib.request
import urllib.error

from bugfix_automation.approval_api import serve_api
from bugfix_automation.config import Config


def serve(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    web_port = port or config.approval_web_port
    api_thread = threading.Thread(target=serve_api, args=(config, host, config.approval_api_port), daemon=True)
    api_thread.start()

    web_dir = Path(__file__).resolve().parents[1] / "approval-web"
    env = os.environ.copy()
    env["BUGFIX_API_URL"] = f"http://{host}:{config.approval_api_port}"
    print(f"审批台启动：http://{host}:{web_port}")
    print(f"审批 API：http://{host}:{config.approval_api_port}")
    if _frontend_is_healthy(host, web_port):
        print(f"审批台端口 {web_port} 已在运行，保持现有前端进程，只启动审批 API。")
        api_thread.join()
        return
    if _port_is_open(host, web_port):
        print(f"审批台端口 {web_port} 被占用但未响应，正在强制清理旧进程...")
        _kill_port(web_port)
    if not (web_dir / "node_modules").exists():
        print("首次启动需要安装审批台前端依赖，正在执行 npm install ...")
        subprocess.run(["npm", "install"], cwd=web_dir, check=True)
    subprocess.run(["npm", "run", "dev", "--", "--hostname", host, "--port", str(web_port)], cwd=web_dir, env=env, check=True)


def serve_api_only(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    serve_api(config, host=host, port=port or config.approval_api_port)


def _kill_port(port: int) -> None:
    """Kill all processes listening on the given port using SIGKILL."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True,
        )
        pids = result.stdout.strip().splitlines()
        for pid in pids:
            try:
                subprocess.run(["kill", "-9", pid], check=False)
            except Exception:
                pass
        if pids:
            import time; time.sleep(0.5)
    except Exception:
        pass


def _frontend_is_healthy(host: str, port: int) -> bool:
    """Return True only if the frontend is actually serving HTTP responses."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=1) as resp:
            return resp.status < 500
    except Exception:
        return False


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0
