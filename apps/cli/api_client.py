"""Thin HTTP client wrapper for the CLI."""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from .errors import ApiError, CliError

DEFAULT_TIMEOUT = 10.0


def format_api_error(status_code: int, body: Optional[str]) -> str:
    """Format API error message based on status code."""
    prefix_map = {
        400: "Validation error",
        404: "Not found",
        409: "Conflict",
        422: "Validation failed",
    }
    prefix = prefix_map.get(status_code, f"HTTP {status_code}")
    detail = ""
    if body:
        try:
            import json
            data = json.loads(body)
            detail = data.get("detail", body)
        except Exception:
            detail = body[:200] if len(body) > 200 else body
    return f"{prefix}: {detail}" if detail else prefix


class ApiClient:
    def __init__(self, base_url: str, headers: Dict[str, str], timeout: float = DEFAULT_TIMEOUT, verbose: bool = False):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.verbose = verbose
        self._client = httpx.Client(headers=headers, timeout=self.timeout)

    def close(self) -> None:
        self._client.close()

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return urljoin(self.base_url, path)

    def _log(self, method: str, url: str, status: Optional[int] = None) -> None:
        if self.verbose:
            suffix = f" -> {status}" if status is not None else ""
            print(f"{method} {url}{suffix}")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(path)
        try:
            response = self._client.get(url, params=params)
        except httpx.RequestError as exc:
            raise CliError(f"Network error: {exc}") from exc

        self._log("GET", url, response.status_code)

        if response.status_code >= 400:
            text = response.text
            raise ApiError(response.status_code, response.reason_phrase, body=text)
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(path)
        try:
            response = self._client.post(url, json=json_body, params=params)
        except httpx.RequestError as exc:
            raise CliError(f"Network error: {exc}") from exc

        self._log("POST", url, response.status_code)

        if response.status_code >= 400:
            text = response.text
            raise ApiError(response.status_code, format_api_error(response.status_code, text), body=text)
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    def put(self, path: str, json_body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(path)
        try:
            response = self._client.put(url, json=json_body, params=params)
        except httpx.RequestError as exc:
            raise CliError(f"Network error: {exc}") from exc

        self._log("PUT", url, response.status_code)

        if response.status_code >= 400:
            text = response.text
            raise ApiError(response.status_code, format_api_error(response.status_code, text), body=text)
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover
        self.close()

