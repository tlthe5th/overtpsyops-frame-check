import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from forensics import analyze_video

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
OUT_DIR = os.path.join(BASE_DIR, "proof_pack")


class ForensicsHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            if not os.path.isfile(INDEX_PATH):
                self.send_error(404, "index.html not found")
                return
            with open(INDEX_PATH, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self.send_error(404, "Not found")
            return

        query = parse_qs(parsed.query)

        def get_int(key: str, default: int) -> int:
            val = query.get(key, [str(default)])[0]
            return int(val)

        def get_str(key: str, default: str = "") -> str:
            return query.get(key, [default])[0]

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._send_json(400, {"ok": False, "error": "Empty video upload."})
            return

        raw_name = os.path.basename(get_str("filename", "upload.mp4")) or "upload.mp4"
        _, ext = os.path.splitext(raw_name)
        suffix = ext if ext else ".mp4"

        try:
            f_prev = get_int("f_prev", 1)
            f_targ = get_int("f_targ", 2)
            f_next = get_int("f_next", 3)
            roi = (get_int("y1", 40), get_int("y2", 80), get_int("x1", 60), get_int("x2", 100))
            quiet = (get_int("q1", 1), get_int("q2", 2))
            provenance = {
                "source": get_str("source", ""),
                "uploader": get_str("uploader", ""),
                "event_time": get_str("event_time", ""),
                "download_date": get_str("download_date", ""),
            }

            with tempfile.TemporaryDirectory() as tmp_dir:
                temp_video = os.path.join(tmp_dir, f"input{suffix}")
                remaining = content_length
                with open(temp_video, "wb") as out_f:
                    while remaining > 0:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            break
                        out_f.write(chunk)
                        remaining -= len(chunk)

                res = analyze_video(
                    video_path=temp_video,
                    f_prev_idx=f_prev,
                    f_target_idx=f_targ,
                    f_next_idx=f_next,
                    roi=roi,
                    quiet_pair=quiet,
                    out_dir=OUT_DIR,
                    provenance=provenance,
                )

            report_path = os.path.join(OUT_DIR, "report.md")
            with open(report_path, "r", encoding="utf-8") as rf:
                report_md = rf.read()

            self._send_json(200, {
                "ok": True,
                "sha256": res["sha256"],
                "cadence": res["cadence_pattern"],
                "report_markdown": report_md,
            })
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, format, *args):
        return


def main():
    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), ForensicsHandler)
    print(f"overtpsyops-frame-check UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
