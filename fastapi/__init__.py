from typing import Any, Callable, Dict, List, Tuple


class APIRouter:
    def __init__(self):
        self.routes: List[Tuple[str, str, Callable[..., Any]]] = []

    def get(self, path: str):
        def decorator(func: Callable[..., Any]):
            self.routes.append(("GET", path, func))
            return func

        return decorator


class FastAPI:
    def __init__(self, title: str | None = None):
        self.title = title
        self.routes: List[Tuple[str, str, Callable[..., Any]]] = []

    def get(self, path: str):
        def decorator(func: Callable[..., Any]):
            self.routes.append(("GET", path, func))
            return func

        return decorator

    def include_router(self, router: APIRouter, prefix: str = ""):
        for method, path, func in router.routes:
            self.routes.append((method, f"{prefix}{path}", func))


class Response:
    def __init__(self, status_code: int = 200, json_body: Any | None = None):
        self.status_code = status_code
        self._json = json_body

    def json(self):
        return self._json


class TestClient:
    def __init__(self, app: FastAPI):
        self.app = app

    def get(self, path: str):
        for method, route_path, func in self.app.routes:
            if method == "GET" and route_path == path:
                result = func()
                return Response(status_code=200, json_body=result)
        return Response(status_code=404, json_body={"detail": "Not Found"})


# Prevent pytest from treating TestClient as a test container
TestClient.__test__ = False


# Expose testclient for compatibility
import types

testclient = types.SimpleNamespace(TestClient=TestClient)
