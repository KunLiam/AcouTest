import json
import os
import subprocess
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from output_paths import DIR_SCREENSHOTS, get_output_dir


class AcouTestControlApi:
    """本地 HTTP 控制接口（给 OpenClaw 调用）。"""

    def __init__(self, app, host="127.0.0.1", port=8765, token="acoutest-local-token"):
        self.app = app
        self.host = host
        self.port = int(port)
        self.token = token or ""
        self.httpd = None
        self.thread = None
        self.actual_port = None
        self._activity_lock = threading.Lock()
        self.last_request_ts = 0.0
        self.last_client_ip = ""
        self.last_path = ""
        self.request_count = 0

    def start(self):
        handler_cls = self._build_handler()
        last_err = None
        for p in range(self.port, self.port + 20):
            try:
                self.httpd = ThreadingHTTPServer((self.host, p), handler_cls)
                self.actual_port = p
                break
            except OSError as e:
                last_err = e
        if self.httpd is None:
            raise RuntimeError(f"HTTP接口启动失败: {last_err}")

        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return {
            "host": self.host,
            "port": self.actual_port,
            "token_hint": self.token,
        }

    def stop(self):
        try:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None
        self.thread = None

    def _build_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _mark_activity(self):
                try:
                    client_ip = ""
                    if isinstance(self.client_address, tuple) and self.client_address:
                        client_ip = str(self.client_address[0] or "")
                    outer._record_activity(client_ip=client_ip, path=self.path)
                except Exception:
                    pass

            def _send_json(self, code, payload):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json_body(self):
                try:
                    n = int(self.headers.get("Content-Length", "0") or "0")
                except Exception:
                    n = 0
                if n <= 0:
                    return {}
                raw = self.rfile.read(n).decode("utf-8", errors="replace")
                if not raw.strip():
                    return {}
                return json.loads(raw)

            def _is_authed(self):
                if not outer.token:
                    return True
                token = (self.headers.get("X-Api-Token") or "").strip()
                if token == outer.token:
                    return True
                q = parse_qs(urlparse(self.path).query or "")
                return (q.get("token", [""])[0] or "").strip() == outer.token

            def _auth_or_401(self):
                if not self._is_authed():
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return False
                return True

            def do_GET(self):
                self._mark_activity()
                parsed = urlparse(self.path)
                if parsed.path in ("/health", "/api/health"):
                    return self._send_json(
                        200,
                        {
                            "ok": True,
                            "name": "AcouTest Control API",
                            "port": outer.actual_port,
                        },
                    )
                if not self._auth_or_401():
                    return
                if parsed.path in ("/api/actions",):
                    return self._send_json(200, {"ok": True, "actions": sorted(list(outer._supported_actions()))})
                if parsed.path in ("/api/status",):
                    try:
                        data = outer._run_on_ui_thread(outer._get_status)
                        return self._send_json(200, {"ok": True, "data": data})
                    except Exception as e:
                        return self._send_json(500, {"ok": False, "error": str(e)})
                if parsed.path in ("/api/devices",):
                    try:
                        data = outer._run_on_ui_thread(outer._get_devices)
                        return self._send_json(200, {"ok": True, "data": data})
                    except Exception as e:
                        return self._send_json(500, {"ok": False, "error": str(e)})
                return self._send_json(404, {"ok": False, "error": "not_found"})

            def do_POST(self):
                self._mark_activity()
                parsed = urlparse(self.path)
                if not self._auth_or_401():
                    return
                if parsed.path not in ("/api/action",):
                    return self._send_json(404, {"ok": False, "error": "not_found"})
                try:
                    payload = self._read_json_body()
                except Exception as e:
                    return self._send_json(400, {"ok": False, "error": f"invalid_json: {e}"})

                action = str(payload.get("action") or "").strip()
                params = payload.get("params") or {}
                if not action:
                    return self._send_json(400, {"ok": False, "error": "missing action"})
                try:
                    result = outer._run_on_ui_thread(lambda: outer._execute_action(action, params))
                    return self._send_json(200, {"ok": True, "action": action, "result": result})
                except Exception as e:
                    return self._send_json(400, {"ok": False, "action": action, "error": str(e)})

            def log_message(self, _format, *args):
                return

        return Handler

    def _log(self, message):
        cb = getattr(self.app, "append_openclaw_log", None)
        if callable(cb):
            try:
                cb(message)
            except Exception:
                pass

    def _record_activity(self, client_ip, path):
        now = time.time()
        with self._activity_lock:
            self.last_request_ts = now
            self.last_client_ip = client_ip or ""
            self.last_path = path or ""
            self.request_count += 1
            req_count = self.request_count
        cb = getattr(self.app, "on_control_api_activity", None)
        if callable(cb):
            try:
                cb(
                    {
                        "ts": now,
                        "client_ip": client_ip or "",
                        "path": path or "",
                        "request_count": req_count,
                    }
                )
            except Exception:
                pass
        self._log(f"HTTP {path or '/'} from {client_ip or 'unknown'}")

    def _run_on_ui_thread(self, fn, timeout_s=30):
        done = threading.Event()
        box = {}

        def _call():
            try:
                box["result"] = fn()
            except Exception as e:
                box["error"] = e
                box["trace"] = traceback.format_exc()
            finally:
                done.set()

        self.app.root.after(0, _call)
        if not done.wait(timeout_s):
            raise TimeoutError(f"UI执行超时({timeout_s}s)")
        if "error" in box:
            raise RuntimeError(f"{box['error']}\n{box.get('trace', '')}".strip())
        return box.get("result")

    def _supported_actions(self):
        return {
            "refresh_devices",
            "select_device",
            "start_mic_test",
            "stop_mic_test",
            "start_logcat_capture",
            "stop_logcat_capture",
            "run_multichannel_test",
            "stop_multichannel_test",
            "take_screenshot",
        }

    def _get_devices(self):
        self.app.refresh_devices()
        values = []
        try:
            values = list(getattr(self.app, "device_combobox", {}).get("values", []))
        except Exception:
            try:
                values = list(self.app.device_combobox["values"])
            except Exception:
                values = []
        return {
            "devices": values,
            "selected_device": getattr(self.app, "selected_device", None),
            "device_var": getattr(self.app, "device_var", None).get() if hasattr(self.app, "device_var") else "",
        }

    def _get_status(self):
        logcat_proc = getattr(self.app, "logcat_process", None)
        wait_proc = getattr(self.app, "logcat_wait_process", None)
        return {
            "selected_device": getattr(self.app, "selected_device", None),
            "device_var": getattr(self.app, "device_var", None).get() if hasattr(self.app, "device_var") else "",
            "mic_is_testing": bool(getattr(self.app, "mic_is_testing", False)),
            "logcat_capturing": bool(logcat_proc),
            "logcat_waiting_device": bool(wait_proc),
            "status_text": getattr(self.app, "status_var", None).get() if hasattr(self.app, "status_var") else "",
        }

    def _ensure_device_online(self):
        if not self.app.check_device_selected():
            raise RuntimeError("请先在主界面选择在线设备")

    def _set_var_if_present(self, var_name, value):
        if value is None:
            return
        var = getattr(self.app, var_name, None)
        if var is None:
            return
        try:
            var.set(str(value))
        except Exception:
            pass

    def _take_screenshot_noninteractive(self, save_dir=None):
        self._ensure_device_online()
        target_dir = (save_dir or "").strip() or get_output_dir(DIR_SCREENSHOTS)
        os.makedirs(target_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        local_path = os.path.join(target_dir, filename)

        cmd = self.app.get_adb_command("exec-out screencap -p")
        r = subprocess.run(cmd, shell=True, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError("截图命令执行失败")
        with open(local_path, "wb") as f:
            f.write(r.stdout or b"")
        if not os.path.exists(local_path) or os.path.getsize(local_path) <= 0:
            raise RuntimeError("截图文件为空")
        if hasattr(self.app, "status_var"):
            self.app.status_var.set(f"截图完成: {filename}")
        return {"path": local_path, "filename": filename}

    def _execute_action(self, action, params):
        if action not in self._supported_actions():
            raise RuntimeError(f"unsupported action: {action}")
        old_ctx = getattr(self.app, "_openclaw_action_context", "")
        self.app._openclaw_action_context = action
        p_show = params if isinstance(params, dict) else {}
        self._log(f"action={action} params={p_show}")
        try:
            return self._execute_action_impl(action, params)
        finally:
            self.app._openclaw_action_context = old_ctx

    def _execute_action_impl(self, action, params):
        if action not in self._supported_actions():
            raise RuntimeError(f"unsupported action: {action}")

        if action == "refresh_devices":
            self.app.refresh_devices()
            return self._get_devices()

        if action == "select_device":
            device_id = str((params or {}).get("device_id") or "").strip()
            if not device_id:
                raise RuntimeError("params.device_id 不能为空")
            self.app.refresh_devices()
            values = []
            try:
                values = list(self.app.device_combobox["values"])
            except Exception:
                values = []
            if device_id not in values:
                raise RuntimeError(f"设备不在当前列表中: {device_id}")
            self.app.device_var.set(device_id)
            self.app.on_device_selected()
            self._ensure_device_online()
            return {"selected_device": getattr(self.app, "selected_device", None)}

        if action == "start_mic_test":
            p = params or {}
            self._set_var_if_present("mic_count_var", p.get("mic_count"))
            self._set_var_if_present("pcm_device_var", p.get("pcm_device"))
            self._set_var_if_present("device_id_var", p.get("device_id"))
            self._set_var_if_present("rate_var", p.get("rate"))
            self._set_var_if_present("mic_save_path_var", p.get("save_path"))
            self.app.start_mic_test()
            return {"mic_is_testing": bool(getattr(self.app, "mic_is_testing", False))}

        if action == "stop_mic_test":
            self.app.stop_mic_test()
            return {"mic_is_testing": bool(getattr(self.app, "mic_is_testing", False))}

        if action == "start_logcat_capture":
            p = params or {}
            self._set_var_if_present("logcat_save_path_var", p.get("save_path"))
            self._set_var_if_present("logcat_filter_var", p.get("filter"))
            self._set_var_if_present("logcat_auto_stop_var", p.get("auto_stop_seconds"))
            self.app.start_logcat_capture()
            return {"logcat_started": True}

        if action == "stop_logcat_capture":
            self.app.stop_logcat_capture()
            return {"logcat_started": False}

        if action == "run_multichannel_test":
            p = params or {}
            self._set_var_if_present("multi_rate_var", p.get("rate"))
            self._set_var_if_present("multi_bit_var", p.get("bit"))
            self._set_var_if_present("multichannel_preset_var", p.get("preset"))
            self._set_var_if_present("multichannel_play_device_var", p.get("play_device"))
            self.app.run_multichannel_test()
            return {"started": True}

        if action == "stop_multichannel_test":
            self.app.stop_multichannel_test()
            return {"stopped": True}

        if action == "take_screenshot":
            p = params or {}
            return self._take_screenshot_noninteractive(save_dir=p.get("save_path"))

        raise RuntimeError(f"unsupported action: {action}")
