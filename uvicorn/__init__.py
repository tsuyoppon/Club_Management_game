def run(app, host: str = "127.0.0.1", port: int = 8000, **kwargs):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            for method, path, func in getattr(app, "routes", []):
                if method == "GET" and path == self.path:
                    data = func()
                    body = json.dumps(data).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            self.send_response(404)
            self.end_headers()

    server = HTTPServer((host, port), Handler)
    server.serve_forever()


def main():
    import importlib
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: uvicorn module:app")
    target = sys.argv[1]
    module_name, app_name = target.split(":")
    module = importlib.import_module(module_name)
    app = getattr(module, app_name)
    run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
