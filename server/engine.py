import subprocess
import threading
import re
from typing import Optional


class PikafishEngine:
    def __init__(self, path: str, depth: int = 20, threads: int = 4, hash_mb: int = 128):
        self.depth = depth
        self._lock = threading.Lock()
        self._proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._send("uci")
        self._send(f"setoption name Threads value {threads}")
        self._send(f"setoption name Hash value {hash_mb}")
        self._send("isready")
        self._wait_for("readyok")

    def _send(self, cmd: str):
        self._proc.stdin.write(cmd + "\n")
        self._proc.stdin.flush()

    def _wait_for(self, token: str) -> list[str]:
        lines = []
        for line in self._proc.stdout:
            line = line.strip()
            lines.append(line)
            if line.startswith(token):
                return lines
        return lines

    def analyze(self, fen: str) -> dict:
        with self._lock:
            self._send("ucinewgame")
            self._send(f"position fen {fen}")
            self._send(f"go depth {self.depth}")
            lines = self._wait_for("bestmove")

        best_move = ""
        score = 0.0
        pv = ""
        for line in reversed(lines):
            if line.startswith("info") and "score cp" in line:
                m = re.search(r"score cp (-?\d+)", line)
                if m:
                    score = int(m.group(1)) / 100.0
                m = re.search(r" pv (.+)", line)
                if m:
                    pv = m.group(1).strip()
                break
            if line.startswith("info") and "score mate" in line:
                m = re.search(r"score mate (-?\d+)", line)
                if m:
                    mate = int(m.group(1))
                    score = 999.0 if mate > 0 else -999.0
                m = re.search(r" pv (.+)", line)
                if m:
                    pv = m.group(1).strip()
                break

        for line in lines:
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2:
                    best_move = parts[1]
                break

        return {"score": score, "best_move": best_move, "pv": pv}

    def close(self):
        self._send("quit")
        self._proc.wait()
