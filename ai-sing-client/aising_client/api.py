from pathlib import Path
import json
import logging
import mimetypes
import sys
import time

import requests


DEFAULT_BASE_URL = "https://xxxx/sing-api"
LOGGER_NAME = "aising_client.api"


logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = True


class ApiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def login(self, username: str, password: str) -> dict:
        response = self._request(
            "POST",
            f"{self.base_url}/api/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        self.token = data.get("token", "")
        return data

    def me(self) -> dict:
        response = self._request("GET", f"{self.base_url}/api/me", headers=self.auth_headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def logout(self) -> None:
        try:
            if self.token:
                response = self._request("POST", f"{self.base_url}/api/logout", headers=self.auth_headers(), timeout=10)
                response.raise_for_status()
        finally:
            self.token = ""

    def create_voice_train_job(self, path: Path) -> dict:
        uploaded = self.upload_to_oss(path, "voice_train")
        response = self._request(
            "POST",
            f"{self.base_url}/api/jobs/voice-train/complete",
            json=uploaded,
            headers=self.auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_song_process_job(self, path: Path, lyrics_path: Path, task_name: str) -> dict:
        task_name = task_name.strip() or path.stem
        audio = self.upload_to_oss(path, "song_process")
        lyrics = self.upload_to_oss(lyrics_path, "song_lyrics")
        response = self._request(
            "POST",
            f"{self.base_url}/api/jobs/song-process/complete",
            json={"task_name": task_name, "audio": audio, "lyrics": lyrics},
            headers=self.auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def list_jobs(self, user_id: int | None = None) -> list[dict]:
        response = self._request("GET", f"{self.base_url}/api/jobs", headers=self.auth_headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def download_job(self, job_id: int, target: Path) -> Path:
        response = self._request(
            "GET",
            f"{self.base_url}/api/jobs/{job_id}/download",
            headers=self.auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target

    def download_job_file(self, job_id: int, file_kind: str, target: Path) -> Path:
        response = self._request(
            "GET",
            f"{self.base_url}/api/jobs/{job_id}/files/{file_kind}",
            headers=self.auth_headers(),
            timeout=30,
        )
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target

    def delete_job(self, job_id: int) -> None:
        response = self._request(
            "DELETE",
            f"{self.base_url}/api/jobs/{job_id}",
            headers=self.auth_headers(),
            timeout=10,
        )
        response.raise_for_status()

    def download_url(self, url: str, target: Path, progress_callback=None) -> Path:
        response = self._request("GET", url, stream=True, timeout=60)
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        total = int(response.headers.get("content-length") or 0)
        downloaded = 0
        with target.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                file_obj.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)
        return target

    def download_job_file_from_job(self, job: dict, file_kind: str, target: Path, progress_callback=None) -> Path:
        url = self.job_file_url(job, file_kind)
        if url:
            return self.download_url(url, target, progress_callback)
        return self.download_job_file(int(job["id"]), file_kind, target)

    def job_file_url(self, job: dict, file_kind: str) -> str:
        try:
            metadata = json.loads(job.get("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            return ""
        output_files = metadata.get("output_files")
        if not isinstance(output_files, dict):
            return ""
        item = output_files.get(file_kind)
        if not isinstance(item, dict):
            return ""
        url = item.get("public_url")
        return url if isinstance(url, str) else ""

    def upload_to_oss(self, path: Path, category: str) -> dict:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        presign_response = self._request(
            "POST",
            f"{self.base_url}/api/oss/presign-upload",
            json={"category": category, "filename": path.name, "content_type": content_type},
            headers=self.auth_headers(),
            timeout=10,
        )
        presign_response.raise_for_status()
        upload_info = presign_response.json()
        with path.open("rb") as file_obj:
            upload_response = self._request(
                "PUT",
                upload_info["upload_url"],
                data=file_obj,
                headers=upload_info.get("headers") or {"Content-Type": content_type},
                timeout=300,
            )
        upload_response.raise_for_status()
        return {
            "object_key": upload_info["object_key"],
            "public_url": upload_info["public_url"],
            "filename": path.name,
            "content_type": content_type,
        }

    def profile(self) -> dict:
        response = self._request("GET", f"{self.base_url}/api/profile", headers=self.auth_headers(), timeout=10)
        response.raise_for_status()
        return response.json()

    def credit_transactions(self) -> list[dict]:
        response = self._request(
            "GET",
            f"{self.base_url}/api/credit-transactions",
            headers=self.auth_headers(),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def public_support(self) -> dict:
        response = self._request("GET", f"{self.base_url}/api/public/support", timeout=10)
        response.raise_for_status()
        return response.json()

    def public_config(self) -> dict:
        response = self._request("GET", f"{self.base_url}/api/public/config", timeout=10)
        response.raise_for_status()
        return response.json()

    def _upload(self, route: str, path: Path) -> dict:
        with path.open("rb") as file_obj:
            response = self._request(
                "POST",
                f"{self.base_url}{route}",
                files={"file": (path.name, file_obj)},
                headers=self.auth_headers(),
                timeout=60,
            )
        response.raise_for_status()
        return response.json()

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _request(self, method: str, url: str, **kwargs):
        method = method.upper()
        started = time.perf_counter()
        logger.info("API request %s %s %s", method, url, self._safe_request_summary(kwargs))
        try:
            response = getattr(requests, method.lower())(url, **kwargs)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("API error %s %s elapsed_ms=%s error=%s", method, url, elapsed_ms, exc)
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        status = getattr(response, "status_code", "ok")
        logger.info("API response %s %s status=%s elapsed_ms=%s", method, url, status, elapsed_ms)
        return response

    def _safe_request_summary(self, kwargs: dict) -> dict:
        summary = {}
        if "timeout" in kwargs:
            summary["timeout"] = kwargs["timeout"]
        if kwargs.get("stream"):
            summary["stream"] = True
        headers = kwargs.get("headers") or {}
        if headers:
            summary["headers"] = {
                key: ("<redacted>" if key.lower() == "authorization" else value)
                for key, value in headers.items()
            }
        if isinstance(kwargs.get("json"), dict):
            summary["json"] = self._redact_dict(kwargs["json"])
        if "files" in kwargs:
            summary["files"] = list(kwargs["files"].keys()) if isinstance(kwargs["files"], dict) else "<provided>"
        if "data" in kwargs:
            summary["data"] = "<stream>" if hasattr(kwargs["data"], "read") else "<provided>"
        return summary

    def _redact_dict(self, payload: dict) -> dict:
        redacted = {}
        sensitive_keys = {"password", "token", "active_token", "authorization"}
        for key, value in payload.items():
            if key.lower() in sensitive_keys:
                redacted[key] = "<redacted>"
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            else:
                redacted[key] = value
        return redacted
