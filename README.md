# 视频前 5 秒截图工具

这是一个用 Python 编写的小应用。启动后会打开一个本地网页，你可以把视频文件拖进去，程序会自动截取前 5 秒的截图，并在页面中展示和下载。

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
python3 app.py
```

启动后打开浏览器访问：

```text
http://127.0.0.1:5000
```

## 支持格式

- `.mp4`
- `.mov`
- `.mkv`
- `.avi`
- `.m4v`
- `.webm`

## 打包成 Mac App

先安装依赖和打包工具：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
```

执行打包：

```bash
pyinstaller --windowed --onedir --name "视频前5秒截图工具" --add-data "templates:templates" launcher.py
```

打包完成后，应用会出现在：

```text
dist/视频前5秒截图工具.app
```
