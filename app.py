import os
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

import cv2
from flask import Flask, jsonify, render_template, request, send_from_directory


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "GetVideoCover"
UPLOAD_DIR = APP_SUPPORT_DIR / "uploads"
OUTPUT_DIR = APP_SUPPORT_DIR / "outputs"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def build_timestamps(duration_seconds):
    if duration_seconds is None or duration_seconds <= 0:
        return list(range(10))

    limit = min(10, max(int(duration_seconds) + 1, 1))
    timestamps = []
    for second in range(limit):
        if second <= duration_seconds:
            timestamps.append(second)

    return timestamps or [0]


def build_frame_base_name(original_filename):
    file_stem = Path(original_filename).stem.strip() or "video"
    invalid_chars = '/\\:\0'
    for char in invalid_chars:
        file_stem = file_stem.replace(char, "_")

    file_stem = " ".join(file_stem.split())
    return file_stem[:150].rstrip() or "video"


def clear_cache_dir(directory):
    for entry in directory.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def format_file_size(size_bytes):
    size = float(size_bytes)
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return "{} {}".format(int(size), unit)
            return "{:.2f} {}".format(size, unit)
        size /= 1024


def format_duration(duration_seconds):
    if duration_seconds is None or duration_seconds <= 0:
        return "未知"

    total_seconds = int(round(duration_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)
    return "{:02d}:{:02d}".format(minutes, seconds)


def decode_fourcc(fourcc_value):
    if not fourcc_value:
        return "未知"

    value = int(fourcc_value)
    chars = []
    for shift in (0, 8, 16, 24):
        char_code = (value >> shift) & 0xFF
        if char_code:
            chars.append(chr(char_code))
    text = "".join(chars).strip()
    return text or "未知"


def extract_frames(video_path, job_id, original_filename=None):
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("无法打开视频文件")

    fps = capture.get(cv2.CAP_PROP_FPS)
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    codec = decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
    duration = None
    if fps and fps > 0 and frame_count and frame_count > 0:
        duration = frame_count / fps

    output_dir = OUTPUT_DIR / job_id
    output_dir.mkdir(exist_ok=True)
    frame_base_name = build_frame_base_name(original_filename or video_path.name)

    results = []
    for second in build_timestamps(duration):
        if fps and fps > 0:
            frame_index = int(second * fps)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        else:
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)

        ok, frame = capture.read()
        if not ok:
            continue

        filename = "{}_{:02d}s.jpg".format(frame_base_name, second)
        file_path = output_dir / filename
        cv2.imwrite(str(file_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        encoded_filename = quote(filename)
        results.append(
            {
                "name": filename,
                "second": second,
                "preview_url": "/preview/{}/{}".format(job_id, encoded_filename),
                "download_url": "/download/{}/{}".format(job_id, encoded_filename),
                "frame_size_text": format_file_size(file_path.stat().st_size),
                "frame_resolution_text": "{} x {}".format(frame.shape[1], frame.shape[0]),
            }
        )

    capture.release()

    if not results:
        raise ValueError("未能从视频中截取到图片")

    video_info_lines = [
        "文件名：{}".format(original_filename or video_path.name),
        "文件大小：{}".format(format_file_size(video_path.stat().st_size)),
        "分辨率：{}".format("{} x {}".format(width, height) if width and height else "未知"),
        "时长：{}".format(format_duration(duration)),
        "帧率：{}".format("{:.2f} fps".format(fps) if fps and fps > 0 else "未知"),
        "总帧数：{}".format(int(frame_count) if frame_count and frame_count > 0 else "未知"),
        "编码格式：{}".format(codec),
        "文件格式：{}".format(video_path.suffix.lower().lstrip(".") or "未知"),
    ]

    return {
        "frames": results,
        "video_size_text": format_file_size(video_path.stat().st_size),
        "video_resolution_text": "{} x {}".format(width, height) if width and height else "未知",
        "video_info_lines": video_info_lines,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("video")
    if not file or not file.filename:
        return jsonify({"error": "请先选择一个视频文件"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "暂不支持该视频格式"}), 400

    job_id = uuid.uuid4().hex
    original_name = Path(file.filename).name
    upload_suffix = Path(original_name).suffix.lower()
    save_path = UPLOAD_DIR / "{}{}".format(job_id, upload_suffix)
    file.save(save_path)

    try:
        result = extract_frames(save_path, job_id, original_name)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "job_id": job_id,
            "file_name": original_name,
            "cover_url": result["frames"][0]["preview_url"],
            "video_size_text": result["video_size_text"],
            "video_resolution_text": result["video_resolution_text"],
            "video_info_lines": result["video_info_lines"],
            "frames": result["frames"],
        }
    )


@app.route("/preview/<job_id>/<filename>")
def preview(job_id, filename):
    return send_from_directory(OUTPUT_DIR / job_id, filename)


@app.route("/download/<job_id>/<filename>")
def download(job_id, filename):
    return send_from_directory(OUTPUT_DIR / job_id, filename, as_attachment=True)


@app.route("/clear-cache", methods=["POST"])
def clear_cache():
    clear_cache_dir(UPLOAD_DIR)
    clear_cache_dir(OUTPUT_DIR)
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
