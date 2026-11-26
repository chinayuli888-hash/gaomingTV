"""Serve the synthetic H.264 fixtures to the iOS Simulator on loopback only."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent / "fixtures"
PORT = 8765
CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mp4": "video/mp4",
    ".m4s": "video/iso.segment",
}
CHANNELS = (("Test A", "missing.m3u8"), ("Test A", "A/stream.m3u8"),
            ("Test B", "B/stream.m3u8"), ("Test Off", "offline.m3u8"))
CATALOG = "#EXTM3U\n" + "".join(
    f'#EXTINF:-1 group-title="模拟器测试",{name}\nhttp://localhost:{PORT}/{path}\n'
    for name, path in CHANNELS
)


class MediaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.serve(send_body=True)

    def do_HEAD(self):
        self.serve(send_body=False)

    def serve(self, send_body):
        path = urlsplit(self.path).path
        if path == "/catalog.m3u":
            data = CATALOG.encode("utf-8")
            mime = "application/vnd.apple.mpegurl; charset=utf-8"
        elif re.fullmatch(r"/[AB]/(?:stream\.m3u8|init\.mp4|video-0\.m4s)", path):
            source = ROOT / path.lstrip("/")
            data = source.read_bytes()
            mime = CONTENT_TYPES[source.suffix]
        else:
            self.send_error(404)
            return

        code = 200
        start, end = 0, len(data) - 1
        byte_range = self.headers.get("Range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
            if not match or not any(match.groups()):
                self.send_error(416)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), end) if last else end
            else:
                start = max(0, len(data) - int(last))
            if end < start:
                self.send_error(416)
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        self.end_headers()
        if send_body:
            self.wfile.write(data[start:end + 1])


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), MediaHandler).serve_forever()
