"""Local-only browser interface for running one JavSP task at a time."""
import json
import hashlib
import os
from pathlib import Path
import re
import secrets
import string
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from collections import deque
from contextlib import asynccontextmanager

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from javsp.config import Cfg


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JAVSP_WEB_DATA", ROOT)).resolve()
CONFIG = DATA_DIR / "config.yml"
TOKEN = secrets.token_urlsafe(32)
lock = threading.RLock()
process = None
task_active = False
lines = deque(maxlen=3000)
exit_code = None


@asynccontextmanager
async def lifespan(_app):
    yield
    shutdown()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


class ConfigInput(BaseModel):
    text: str
    revision: str


class QuickConfigInput(BaseModel):
    text: str
    directory: str
    proxy: str
    minimum_size: str
    move_files: bool
    skip_nfo_dir: bool
    normal_sources: list[str]
    fc2_sources: list[str]


class StartInput(BaseModel):
    directory: str
    confirm: bool


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0].lower()
    if host not in ("127.0.0.1", "localhost"):
        return HTMLResponse("Invalid host", status_code=403)
    if request.method != "GET" and not secrets.compare_digest(
        request.headers.get("x-javsp-token", ""), TOKEN
    ):
        return HTMLResponse("Invalid token", status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    )
    return response


def parse_config(text):
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("configuration must be a mapping")
        cfg = Cfg.model_validate(data)
        for pattern in (cfg.scanner.ignored_id_pattern
                        + cfg.scanner.ignored_folder_name_pattern
                        + cfg.summarizer.cover.crop.on_id_pattern):
            re.compile(pattern)
        fields = {'num', 'title', 'rawtitle', 'actress', 'score', 'censor',
                  'serial', 'director', 'producer', 'publisher', 'date',
                  'year', 'label', 'genre'}
        templates = [cfg.summarizer.path.output_folder_pattern,
                     cfg.summarizer.path.basename_pattern,
                     cfg.summarizer.nfo.basename_pattern,
                     cfg.summarizer.nfo.title_pattern,
                     cfg.summarizer.cover.basename_pattern,
                     cfg.summarizer.fanart.basename_pattern,
                     *cfg.summarizer.nfo.custom_genres_fields,
                     *cfg.summarizer.nfo.custom_tags_fields]
        for template in templates:
            for _, field, spec, conversion in string.Formatter().parse(template):
                if field is not None and (field not in fields or spec or conversion):
                    raise ValueError(f"Unsupported template field: {field}")
        return data
    except (yaml.YAMLError, ValidationError, ValueError, TypeError, re.error) as exc:
        raise HTTPException(400, f"Invalid configuration: {exc}") from exc


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
            prefix=".javsp-", suffix=".tmp", newline="\n"
        ) as f:
            name = f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@app.get("/", response_class=HTMLResponse)
def index():
    html = (ROOT / "javsp" / "ui" / "index.html").read_text(encoding="utf-8")
    return html.replace("__JAVSP_TOKEN__", json.dumps(TOKEN))


@app.get("/api/config")
def get_config():
    raw = CONFIG.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    result = {"text": text, "input_directory": None, "quick": None,
              "revision": hashlib.sha256(raw).hexdigest(), "error": None}
    try:
        data = parse_config(text)
    except HTTPException as exc:
        result["error"] = str(exc.detail)
    else:
        result["input_directory"] = data["scanner"].get("input_directory")
        result["quick"] = quick_values(data)
    return result


def quick_values(data):
    return {
        "proxy": data["network"].get("proxy_server") or "",
        "minimum_size": str(data["scanner"]["minimum_size"]),
        "move_files": data["summarizer"]["move_files"],
        "skip_nfo_dir": data["scanner"]["skip_nfo_dir"],
        "normal_sources": data["crawler"]["selection"]["normal"],
        "fc2_sources": data["crawler"]["selection"]["fc2"],
    }


@app.post("/api/config/quick-preview")
def quick_preview(payload: QuickConfigInput):
    data = parse_config(payload.text)
    data["scanner"]["input_directory"] = payload.directory.strip() or None
    data["scanner"]["minimum_size"] = payload.minimum_size.strip()
    data["scanner"]["skip_nfo_dir"] = payload.skip_nfo_dir
    data["network"]["proxy_server"] = payload.proxy.strip() or None
    data["summarizer"]["move_files"] = payload.move_files
    data["crawler"]["selection"]["normal"] = payload.normal_sources
    data["crawler"]["selection"]["fc2"] = payload.fc2_sources
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    parse_config(text)
    return {"text": text}


@app.put("/api/config")
def save_config(payload: ConfigInput):
    parse_config(payload.text)
    with lock:
        if task_active:
            raise HTTPException(409, "A task is running")
        current = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        if not secrets.compare_digest(current, payload.revision):
            raise HTTPException(409, "配置文件已被其他操作修改，请先备份当前编辑内容并重新加载")
        atomic_write(CONFIG, payload.text)
    return {"ok": True}


def collect_output(child, config_path):
    global exit_code, task_active
    try:
        for line in child.stdout:
            with lock:
                if process is child:
                    lines.append(line.rstrip("\r\n")[-16000:])
    except (OSError, ValueError) as exc:
        with lock:
            if process is child:
                lines.append(f"Failed to read task output: {exc}")
    finally:
        code = child.wait()
        try:
            config_path.unlink(missing_ok=True)
        finally:
            with lock:
                if process is child:
                    exit_code = code
                    task_active = False


@app.post("/api/start")
def start(payload: StartInput):
    global process, exit_code, task_active
    if not payload.confirm:
        raise HTTPException(400, "Confirm file changes before starting")
    directory = Path(payload.directory).expanduser()
    if not directory.is_absolute() or not directory.is_dir():
        raise HTTPException(400, "Select an existing absolute directory")
    with lock:
        if task_active:
            raise HTTPException(409, "A task is already running")
        data = parse_config(CONFIG.read_text(encoding="utf-8"))
        data["scanner"]["input_directory"] = str(directory.resolve())
        data["scanner"]["manual"] = False
        data["other"]["interactive"] = False
        data["other"]["check_update"] = False
        data["other"]["auto_update"] = False
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        config_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".yml", prefix=".task-",
                dir=DATA_DIR, delete=False
            ) as f:
                config_path = Path(f.name)
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        except Exception:
            if config_path is not None:
                config_path.unlink(missing_ok=True)
            raise
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith("JAVSP_")}
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["JAVSP_AUDIT_LOG"] = str(DATA_DIR / "FileMove.log")
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "javsp", "-c", str(config_path)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                errors="replace", env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            config_path.unlink(missing_ok=True)
            raise
        lines.clear()
        exit_code = None
        task_active = True
        threading.Thread(
            target=collect_output, args=(process, config_path), daemon=True
        ).start()
    return {"ok": True}


@app.get("/api/status")
def status():
    with lock:
        return {
            "running": task_active,
            "exit_code": exit_code,
            "lines": list(lines),
        }


@app.post("/api/stop")
def stop():
    with lock:
        if process is None or process.poll() is not None:
            raise HTTPException(409, "No task is running")
        process.terminate()
    return {"ok": True}


def shutdown():
    with lock:
        child = process if task_active else None
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def entry():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        raise SystemExit(f"Missing configuration: {CONFIG}")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning"))
    if "--open-browser" in sys.argv:
        def open_after_start():
            deadline = time.monotonic() + 15
            while not server.started and not server.should_exit and time.monotonic() < deadline:
                time.sleep(.1)
            if server.started and not server.should_exit:
                webbrowser.open("http://127.0.0.1:8765")
        threading.Thread(target=open_after_start, daemon=True).start()
    server.run()


if __name__ == "__main__":
    entry()
