import os
import shutil
import socket
import threading
import time
import uuid
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from app import OUTPUT_DIR, allowed_file, app, extract_frames


main_window = None


class AppApi:
    def __init__(self):
        self.source_dir = ''

    def set_source_dir(self, file_path):
        if file_path:
            self.source_dir = str(Path(file_path).resolve().parent)

    def build_save_path(self, filename):
        target_dir = Path(self.source_dir) if self.source_dir else Path.home() / "Downloads"
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / filename
        if not target_path.exists():
            return target_path

        stem = target_path.stem
        suffix = target_path.suffix
        index = 1
        while True:
            candidate = target_dir / "{}_{}{}".format(stem, index, suffix)
            if not candidate.exists():
                return candidate
            index += 1

    def pick_video(self):
        result = main_window.create_file_dialog(
            webview.OPEN_DIALOG,
            directory=self.source_dir,
            allow_multiple=False,
            file_types=("视频文件 (*.mp4;*.mov;*.mkv;*.avi;*.m4v;*.webm)",),
        )
        if not result:
            return {"ok": False, "cancelled": True}

        video_path = Path(result[0] if isinstance(result, (list, tuple)) else result)
        if not allowed_file(video_path.name):
            return {"ok": False, "error": "暂不支持该视频格式"}

        self.set_source_dir(str(video_path))
        job_id = uuid.uuid4().hex
        try:
            result = extract_frames(video_path, job_id, video_path.name)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {
            "ok": True,
            "job_id": job_id,
            "file_name": video_path.name,
            "cover_url": result["frames"][0]["preview_url"],
            "video_size_text": result["video_size_text"],
            "video_resolution_text": result["video_resolution_text"],
            "video_info_lines": result["video_info_lines"] + ["原始路径：{}".format(str(video_path))],
            "frames": result["frames"],
        }

    def save_screenshot(self, job_id, filename):
        source_path = OUTPUT_DIR / job_id / filename
        if not source_path.exists():
            return {"ok": False, "error": "截图文件不存在"}

        target_path = self.build_save_path(filename)
        shutil.copyfile(source_path, target_path)
        return {"ok": True, "path": str(target_path)}


app_api = AppApi()


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(host, port, retries):
    for _ in range(retries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def run_server(host, port):
    app.run(host=host, port=port, debug=False, use_reloader=False)


def handle_drop(event):
    files = event.get("dataTransfer", {}).get("files", [])
    if not files:
        return

    full_path = files[0].get("pywebviewFullPath")
    if full_path:
        app_api.set_source_dir(full_path)


def bind_window(window):
    window.dom.document.events.drop += DOMEventHandler(handle_drop, True, True)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", str(find_free_port())))
    url = "http://{}:{}".format(host, port)

    server_thread = threading.Thread(target=run_server, args=(host, port), daemon=True)
    server_thread.start()

    if not wait_for_server(host, port, 50):
        raise RuntimeError("应用服务启动失败")

    main_window = webview.create_window(
        "视频前5秒截图工具",
        url,
        width=550,
        height=760,
        js_api=app_api,
    )
    webview.start(bind_window, main_window)
