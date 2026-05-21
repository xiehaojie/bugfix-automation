from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import threading
import urllib.request

from bugfix_automation.approval_api import serve_api
from bugfix_automation.config import Config


@dataclass(frozen=True)
class PortProcess:
    pid: str
    command: str


def serve(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    web_port = port or config.approval_web_port
    _exit_if_port_occupied(config.approval_api_port, "审批 API")
    web_processes = _listening_port_processes(web_port)
    reuse_existing_frontend = bool(web_processes and _frontend_is_healthy(host, web_port))
    if web_processes and not reuse_existing_frontend:
        _exit_with_port_processes(web_port, "审批台前端", web_processes)

    api_thread = threading.Thread(target=serve_api, args=(config, host, config.approval_api_port), daemon=True)
    api_thread.start()

    web_dir = Path(__file__).resolve().parents[1] / "approval-web"
    env = os.environ.copy()
    env["BUGFIX_API_URL"] = f"http://{host}:{config.approval_api_port}"
    print(f"审批台启动：http://{host}:{web_port}")
    print(f"审批 API：http://{host}:{config.approval_api_port}")
    if reuse_existing_frontend:
        _print_port_processes(web_port, "审批台前端", web_processes)
        print("检测到已有审批台前端在运行，复用现有前端，只启动审批 API。")
        api_thread.join()
        return
    if not (web_dir / "node_modules").exists():
        print("首次启动需要安装审批台前端依赖，正在执行 npm install ...")
        subprocess.run(["npm", "install"], cwd=web_dir, check=True)
    subprocess.run(["npm", "run", "dev", "--", "--hostname", host, "--port", str(web_port)], cwd=web_dir, env=env, check=True)


def serve_api_only(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    api_port = port or config.approval_api_port
    _exit_if_port_occupied(api_port, "审批 API")
    serve_api(config, host=host, port=api_port)


def _exit_if_port_occupied(port: int, label: str) -> None:
    processes = _listening_port_processes(port)
    if not processes:
        return

    _exit_with_port_processes(port, label, processes)


def _exit_with_port_processes(port: int, label: str, processes: list[PortProcess]) -> None:
    _print_port_processes(port, label, processes)
    print("如确认可以停止旧进程，请执行：")
    for process in processes:
        print(f"  kill {process.pid}")
    raise SystemExit(2)


def _print_port_processes(port: int, label: str, processes: list[PortProcess]) -> None:
    print(f"{label} 端口 {port} 已被占用。")
    print("占用进程：")
    for process in processes:
        print(f"  PID {process.pid}: {process.command}")


def _listening_port_processes(port: int) -> list[PortProcess]:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []

    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    processes: list[PortProcess] = []
    for pid in dict.fromkeys(pids):
        processes.append(PortProcess(pid=pid, command=_process_command(pid)))
    return processes


def _process_command(pid: str) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", pid, "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "<unknown>"
    return result.stdout.strip() or "<unknown>"


def _frontend_is_healthy(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=1) as response:
            return response.status < 500
    except Exception:
        return False
