#!/usr/bin/env python3
"""
chess-coach 菜单栏 App
点击启动：设置系统代理 + 启动 mitmdump + uvicorn
点击停止：关停进程 + 清除系统代理
"""
import subprocess
from pathlib import Path

import rumps

ROOT = Path(__file__).parent
VENV_BIN = ROOT / ".venv" / "bin"
MINIFORGE_BIN = Path("/opt/homebrew/Caskroom/miniforge/base/bin")
PROXY_PORT = 8080
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8888


def _active_interfaces():
    """返回当前活跃的网络接口名列表"""
    try:
        out = subprocess.check_output(["networksetup", "-listallnetworkservices"], text=True)
        return [
            l.strip() for l in out.splitlines()
            if l.strip() and not l.startswith("*")
            and "asterisk" not in l
        ]
    except Exception:
        return ["Wi-Fi"]


def set_proxy(on: bool):
    state = "on" if on else "off"
    for iface in _active_interfaces():
        if on:
            subprocess.run(["networksetup", "-setwebproxy", iface, SERVER_HOST, str(PROXY_PORT)], check=False)
            subprocess.run(["networksetup", "-setsecurewebproxy", iface, SERVER_HOST, str(PROXY_PORT)], check=False)
        subprocess.run(["networksetup", "-setwebproxystate", iface, state], check=False)
        subprocess.run(["networksetup", "-setsecurewebproxystate", iface, state], check=False)


class ChessCoachApp(rumps.App):
    def __init__(self):
        super().__init__("♟", quit_button=None)
        self.menu = [
            rumps.MenuItem("启动监控", callback=self.start),
            rumps.MenuItem("停止监控", callback=self.stop),
            None,
            rumps.MenuItem("打开复盘页", callback=self.open_web),
            None,
            rumps.MenuItem("退出", callback=self.quit_app),
        ]
        self._mitm_proc = None
        self._uvicorn_proc = None
        self._running = False
        self._update_menu()

    def _update_menu(self):
        self.menu["启动监控"].set_callback(None if self._running else self.start)
        self.menu["停止监控"].set_callback(self.stop if self._running else None)
        self.title = "♟●" if self._running else "♟"

    def start(self, _=None):
        if self._running:
            return
        set_proxy(True)
        self._mitm_proc = subprocess.Popen(
            [str(MINIFORGE_BIN / "mitmdump"), "-s", "proxy/jj_addon.py",
             "--listen-port", str(PROXY_PORT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        env = os.environ.copy()
        env["no_proxy"] = "*"
        env["NO_PROXY"] = "*"
        self._uvicorn_proc = subprocess.Popen(
            [str(VENV_BIN / "uvicorn"), "server.main:app",
             "--host", SERVER_HOST, "--port", str(SERVER_PORT)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._running = True
        self._update_menu()
        rumps.notification("象棋教练", "", "监控已启动")

    def stop(self, _=None):
        if not self._running:
            return
        for proc in (self._mitm_proc, self._uvicorn_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._mitm_proc = None
        self._uvicorn_proc = None
        set_proxy(False)
        self._running = False
        self._update_menu()
        rumps.notification("象棋教练", "", "监控已停止")

    def open_web(self, _):
        subprocess.run(["open", f"http://{SERVER_HOST}:{SERVER_PORT}/web/index.html"])

    def quit_app(self, _):
        self.stop()
        rumps.quit_application()


if __name__ == "__main__":
    ChessCoachApp().run()
