import asyncio
import subprocess
import shutil
import json
import os
import time
import hashlib
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.json")

APP_CONFIG: dict = {}
STATE_FILE = "maintainer_state.json"
LOOP_SLEEP_SECONDS = 1
SERVICE_NAME = "openclaw"
CONFIG_FILES: list[str] = []

REMEDIATION_DRY_RUN = True
PROCESS_RESTART_COOLDOWN_SEC = 300
PROCESS_RESTART_MAX_RETRIES = 3
PROCESS_RESTART_RETRY_WINDOW_SEC = 1800

ALERT_WEBHOOK_URL = ""
ALERT_COOLDOWN_SEC = 300
ALERT_HTTP_TIMEOUT_SEC = 5
ALERT_STATUSES = {"warn", "critical", "error"}


def now() -> int:
    return int(time.time())


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {value!r}") from exc


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return parts


def _require_keys(data: dict, keys: list[str], section_name: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"Config section '{section_name}' is missing keys: {', '.join(missing)}")


def _validate_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Config field '{field_name}' must be a positive integer")


def _validate_pct(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value < 0 or value > 100:
        raise ValueError(f"Config field '{field_name}' must be an integer between 0 and 100")


def load_config() -> dict:
    config_path = Path(os.getenv("MAINTAINER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))).expanduser()
    if not config_path.exists():
        raise FileNotFoundError(f"Maintainer config not found: {config_path}")

    with open(config_path) as fh:
        config = json.load(fh)

    _require_keys(config, ["runtime", "enabled_modules", "process", "gpu", "memory", "disk", "config_drift"], "root")

    runtime = config["runtime"]
    process = config["process"]
    gpu = config["gpu"]
    memory = config["memory"]
    disk = config["disk"]
    drift = config["config_drift"]
    sentinel_probe = config.setdefault(
        "sentinel_probe",
        {
            "interval": 30,
            "health_url": "",
            "prom_url": "",
            "prom_match": 'up{job="sentinel"}',
            "prom_min_value": 1.0,
            "latency_warn_ms": 0,
            "http_timeout_sec": 3,
        },
    )

    remediation = config.setdefault(
        "remediation",
        {
            "dry_run": True,
            "process_restart_cooldown_sec": 300,
            "process_restart_max_retries": 3,
            "process_restart_retry_window_sec": 1800,
        },
    )
    alert_sink = config.setdefault(
        "alert_sink",
        {
            "webhook_url": "",
            "cooldown_sec": 300,
            "http_timeout_sec": 5,
        },
    )

    _require_keys(runtime, ["state_file", "loop_sleep_seconds"], "runtime")
    _require_keys(process, ["service_name", "interval"], "process")
    _require_keys(gpu, ["interval", "temp_warn", "temp_crit"], "gpu")
    _require_keys(memory, ["interval", "ram_warn", "swap_crit"], "memory")
    _require_keys(disk, ["interval", "path", "warn_pct", "crit_pct"], "disk")
    _require_keys(drift, ["interval", "files"], "config_drift")
    _require_keys(
        sentinel_probe,
        ["interval", "health_url", "prom_url", "prom_match", "prom_min_value", "latency_warn_ms", "http_timeout_sec"],
        "sentinel_probe",
    )

    runtime["state_file"] = _env_str("MAINTAINER_STATE_FILE", runtime["state_file"])
    runtime["loop_sleep_seconds"] = _env_int("MAINTAINER_LOOP_SLEEP_SECONDS", runtime["loop_sleep_seconds"])
    process["service_name"] = _env_str("MAINTAINER_SERVICE_NAME", process["service_name"])
    enabled_modules = _env_list("MAINTAINER_ENABLED_MODULES", config["enabled_modules"])
    config["enabled_modules"] = enabled_modules
    sentinel_probe["health_url"] = _env_str("SENTINEL_HEALTH_URL", sentinel_probe["health_url"])
    sentinel_probe["prom_url"] = _env_str("SENTINEL_PROM_URL", sentinel_probe["prom_url"])
    sentinel_probe["prom_match"] = _env_str("SENTINEL_PROM_MATCH", sentinel_probe["prom_match"])
    alert_sink["webhook_url"] = _env_str("MAINTAINER_ALERT_WEBHOOK_URL", alert_sink["webhook_url"])
    alert_sink["cooldown_sec"] = _env_int("MAINTAINER_ALERT_COOLDOWN_SEC", alert_sink["cooldown_sec"])
    alert_sink["http_timeout_sec"] = _env_int("MAINTAINER_ALERT_HTTP_TIMEOUT_SEC", alert_sink["http_timeout_sec"])

    _validate_positive_int(runtime["loop_sleep_seconds"], "runtime.loop_sleep_seconds")
    _validate_positive_int(process["interval"], "process.interval")
    _validate_positive_int(gpu["interval"], "gpu.interval")
    _validate_positive_int(memory["interval"], "memory.interval")
    _validate_positive_int(disk["interval"], "disk.interval")
    _validate_positive_int(drift["interval"], "config_drift.interval")
    _validate_positive_int(sentinel_probe["interval"], "sentinel_probe.interval")

    _validate_positive_int(gpu["temp_warn"], "gpu.temp_warn")
    _validate_positive_int(gpu["temp_crit"], "gpu.temp_crit")
    _validate_pct(memory["ram_warn"], "memory.ram_warn")
    _validate_pct(memory["swap_crit"], "memory.swap_crit")
    _validate_pct(disk["warn_pct"], "disk.warn_pct")
    _validate_pct(disk["crit_pct"], "disk.crit_pct")

    if gpu["temp_crit"] <= gpu["temp_warn"]:
        raise ValueError("Config field 'gpu.temp_crit' must be greater than 'gpu.temp_warn'")
    if disk["crit_pct"] <= disk["warn_pct"]:
        raise ValueError("Config field 'disk.crit_pct' must be greater than 'disk.warn_pct'")

    if not isinstance(remediation["dry_run"], bool):
        raise ValueError("Config field 'remediation.dry_run' must be a boolean")
    _validate_positive_int(remediation["process_restart_cooldown_sec"], "remediation.process_restart_cooldown_sec")
    _validate_positive_int(remediation["process_restart_max_retries"], "remediation.process_restart_max_retries")
    _validate_positive_int(remediation["process_restart_retry_window_sec"], "remediation.process_restart_retry_window_sec")

    if not isinstance(alert_sink["webhook_url"], str):
        raise ValueError("Config field 'alert_sink.webhook_url' must be a string")
    _validate_positive_int(alert_sink["cooldown_sec"], "alert_sink.cooldown_sec")
    _validate_positive_int(alert_sink["http_timeout_sec"], "alert_sink.http_timeout_sec")

    if not isinstance(drift["files"], list):
        raise ValueError("Config field 'config_drift.files' must be a list of file paths")
    if not isinstance(sentinel_probe["prom_min_value"], (int, float)):
        raise ValueError("Config field 'sentinel_probe.prom_min_value' must be a number")
    if not isinstance(sentinel_probe["latency_warn_ms"], (int, float)) or sentinel_probe["latency_warn_ms"] < 0:
        raise ValueError("Config field 'sentinel_probe.latency_warn_ms' must be a non-negative number")
    if not isinstance(sentinel_probe["http_timeout_sec"], (int, float)) or sentinel_probe["http_timeout_sec"] <= 0:
        raise ValueError("Config field 'sentinel_probe.http_timeout_sec' must be > 0")

    known_modules = {"process", "gpu", "memory", "disk", "config_drift", "sentinel_probe"}
    unknown = [name for name in enabled_modules if name not in known_modules]
    if unknown:
        raise ValueError(f"Unknown module(s) in enabled_modules: {', '.join(unknown)}")
    if not enabled_modules:
        raise ValueError("enabled_modules cannot be empty")

    return config


def apply_config(config: dict) -> None:
    global APP_CONFIG, STATE_FILE, LOOP_SLEEP_SECONDS, SERVICE_NAME, CONFIG_FILES
    global REMEDIATION_DRY_RUN, PROCESS_RESTART_COOLDOWN_SEC, PROCESS_RESTART_MAX_RETRIES, PROCESS_RESTART_RETRY_WINDOW_SEC
    global ALERT_WEBHOOK_URL, ALERT_COOLDOWN_SEC, ALERT_HTTP_TIMEOUT_SEC
    APP_CONFIG = config
    STATE_FILE = config["runtime"]["state_file"]
    LOOP_SLEEP_SECONDS = config["runtime"]["loop_sleep_seconds"]
    SERVICE_NAME = config["process"]["service_name"]
    CONFIG_FILES = config["config_drift"]["files"]

    remediation = config["remediation"]
    REMEDIATION_DRY_RUN = remediation["dry_run"]
    PROCESS_RESTART_COOLDOWN_SEC = remediation["process_restart_cooldown_sec"]
    PROCESS_RESTART_MAX_RETRIES = remediation["process_restart_max_retries"]
    PROCESS_RESTART_RETRY_WINDOW_SEC = remediation["process_restart_retry_window_sec"]

    alert_sink = config["alert_sink"]
    ALERT_WEBHOOK_URL = alert_sink["webhook_url"]
    ALERT_COOLDOWN_SEC = alert_sink["cooldown_sec"]
    ALERT_HTTP_TIMEOUT_SEC = alert_sink["http_timeout_sec"]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as fh:
        return json.load(fh)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as fh:
        json.dump(state, fh, indent=2)


def get_remediation_state(action: str) -> dict:
    state = load_state()
    return state.setdefault("remediation", {}).setdefault(action, {})


def save_remediation_state(action: str, action_state: dict) -> None:
    state = load_state()
    state.setdefault("remediation", {})[action] = action_state
    save_state(state)


def log(module: str, status: str, message: str = "", data: dict | None = None) -> None:
    entry = {
        "ts": now(),
        "module": module,
        "status": status,
        "message": message,
        "data": data or {},
    }
    print(json.dumps(entry))


def record_module_state(module: str, result: dict) -> None:
    state = load_state()
    state.setdefault("modules", {})[module] = {
        "ts": now(),
        "status": result.get("status", "unknown"),
        "message": result.get("message", ""),
        "data": result.get("data", {}),
    }
    save_state(state)


def _post_webhook(payload: dict) -> tuple[bool, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ALERT_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=ALERT_HTTP_TIMEOUT_SEC) as resp:  # noqa: S310
            status = getattr(resp, "status", 200)
            if 200 <= status < 300:
                return True, f"HTTP {status}"
            return False, f"HTTP {status}"
    except urllib.error.HTTPError as err:
        return False, f"HTTP {err.code}"
    except Exception as err:  # noqa: BLE001
        return False, str(err)


def _build_alert_fingerprint(result: dict) -> str:
    status = result.get("status", "unknown")
    message = result.get("message", "")
    return hashlib.sha256(f"{status}|{message}".encode("utf-8")).hexdigest()


def dispatch_alert(module_name: str, result: dict) -> None:
    if not ALERT_WEBHOOK_URL:
        return

    state = load_state()
    modules_state = state.setdefault("modules", {})
    alerts_state = state.setdefault("alerts", {}).setdefault("modules", {})

    current_status = result.get("status", "unknown")
    previous_status = modules_state.get(module_name, {}).get("status")
    module_alert_state = alerts_state.setdefault(module_name, {})

    event = None
    payload_status = current_status
    payload_message = result.get("message", "")

    if current_status in ALERT_STATUSES:
        fingerprint = _build_alert_fingerprint(result)
        last_sent_ts = int(module_alert_state.get("last_sent_ts", 0))
        last_fingerprint = module_alert_state.get("last_fingerprint", "")
        if last_fingerprint == fingerprint and (now() - last_sent_ts) < ALERT_COOLDOWN_SEC:
            return
        event = "alert"
    elif current_status == "ok" and previous_status in ALERT_STATUSES:
        event = "recovery"
        payload_status = "info"
        payload_message = f"Recovered from {previous_status}"
    else:
        return

    payload = {
        "ts": now(),
        "event": event,
        "module": module_name,
        "status": payload_status,
        "message": payload_message,
        "result": result,
        "recovered_from": previous_status if event == "recovery" else None,
    }

    ok, detail = _post_webhook(payload)
    if ok:
        module_alert_state.update(
            {
                "last_sent_ts": payload["ts"],
                "last_fingerprint": _build_alert_fingerprint(result),
                "last_status": current_status,
                "last_event": event,
                "last_error": "",
            }
        )
    else:
        module_alert_state.update(
            {
                "last_status": current_status,
                "last_event": event,
                "last_error": detail,
                "last_attempt_ts": payload["ts"],
            }
        )
        log("alert_sink", "error", f"Failed to dispatch webhook for {module_name}: {detail}")

    save_state(state)


async def run_cmd(cmd: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return out.decode()


def fetch_url(url: str, timeout_sec: float) -> dict:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status_code": getattr(resp, "status", 200),
                "body": body,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
    except urllib.error.HTTPError as err:
        return {
            "ok": False,
            "status_code": err.code,
            "error": f"HTTP {err.code}",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as err:  # noqa: BLE001
        return {
            "ok": False,
            "status_code": None,
            "error": str(err),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def parse_prom_metric_value(prom_text: str, match: str) -> float | None:
    for raw_line in prom_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if match not in line:
            continue
        try:
            return float(line.split()[-1])
        except ValueError:
            continue
    return None


class MaintainerModule:
    name = "base"
    interval = 60

    async def run(self) -> dict:
        raise NotImplementedError


class ProcessModule(MaintainerModule):
    name = "process"

    def __init__(self, interval: int):
        self.interval = interval

    async def run(self) -> dict:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        status = result.stdout.strip()
        if status != "active":
            return {"status": "critical", "message": f"Service {SERVICE_NAME} is {status}"}
        return {"status": "ok"}


class GPUModule(MaintainerModule):
    name = "gpu"

    def __init__(self, interval: int, temp_warn: int, temp_crit: int):
        self.interval = interval
        self.temp_warn = temp_warn
        self.temp_crit = temp_crit

    async def run(self) -> dict:
        try:
            output = await run_cmd(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ]
            )
            temp, used, total = map(int, output.strip().split(","))
            mem_pct = used / total * 100
            data = {"temp_c": temp, "vram_pct": round(mem_pct, 1)}
            if temp >= self.temp_crit:
                return {"status": "critical", "message": f"GPU temp {temp}C", "data": data}
            if temp >= self.temp_warn:
                return {"status": "warn", "message": f"GPU temp {temp}C", "data": data}
            return {"status": "ok", "data": data}
        except Exception:
            return {"status": "warn", "message": "GPU not detected"}


class MemoryModule(MaintainerModule):
    name = "memory"

    def __init__(self, interval: int, ram_warn: int, swap_crit: int):
        self.interval = interval
        self.ram_warn = ram_warn
        self.swap_crit = swap_crit

    async def run(self) -> dict:
        try:
            import psutil
        except ImportError:
            return {"status": "warn", "message": "psutil not installed; memory checks skipped"}

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        data = {"ram_pct": mem.percent, "swap_pct": swap.percent}
        if swap.percent > self.swap_crit:
            return {"status": "critical", "message": "High swap usage", "data": data}
        if mem.percent > self.ram_warn:
            return {"status": "warn", "message": "High RAM usage", "data": data}
        return {"status": "ok", "data": data}


class DiskModule(MaintainerModule):
    name = "disk"

    def __init__(self, interval: int, path: str, warn_pct: int, crit_pct: int):
        self.interval = interval
        self.path = path
        self.warn_pct = warn_pct
        self.crit_pct = crit_pct

    async def run(self) -> dict:
        total, used, _ = shutil.disk_usage(self.path)
        pct = used / total * 100
        data = {"disk_pct": round(pct, 1), "path": self.path}
        if pct > self.crit_pct:
            return {"status": "critical", "message": "Disk nearly full", "data": data}
        if pct > self.warn_pct:
            return {"status": "warn", "message": "Disk usage high", "data": data}
        return {"status": "ok", "data": data}


class ConfigDriftModule(MaintainerModule):
    name = "config_drift"

    def __init__(self, interval: int):
        self.interval = interval

    async def run(self) -> dict:
        state = load_state()
        hashes = state.get("config_hashes", {})
        changed = []
        for path in CONFIG_FILES:
            if not os.path.exists(path):
                continue
            current_hash = sha256_file(path)
            if hashes.get(path) and hashes[path] != current_hash:
                changed.append(path)
            hashes[path] = current_hash
        state["config_hashes"] = hashes
        save_state(state)
        if changed:
            return {"status": "warn", "message": f"Config changed: {', '.join(changed)}"}
        return {"status": "ok"}


class SentinelProbeModule(MaintainerModule):
    name = "sentinel_probe"

    def __init__(
        self,
        interval: int,
        health_url: str,
        prom_url: str,
        prom_match: str,
        prom_min_value: float,
        latency_warn_ms: float,
        http_timeout_sec: float,
    ):
        self.interval = interval
        self.health_url = health_url
        self.prom_url = prom_url
        self.prom_match = prom_match
        self.prom_min_value = prom_min_value
        self.latency_warn_ms = latency_warn_ms
        self.http_timeout_sec = http_timeout_sec

    async def run(self) -> dict:
        if not self.health_url and not self.prom_url:
            return {"status": "ok", "message": "Sentinel probes disabled"}

        data: dict = {}
        failures: list[str] = []
        warnings: list[str] = []

        if self.health_url:
            health = await asyncio.to_thread(fetch_url, self.health_url, self.http_timeout_sec)
            data["healthz"] = {
                "url": self.health_url,
                "ok": health["ok"],
                "status_code": health.get("status_code"),
                "latency_ms": health.get("latency_ms"),
            }
            if not health["ok"]:
                failures.append(f"healthz failed ({health.get('error', 'unknown')})")
            if self.latency_warn_ms > 0 and health.get("latency_ms", 0) > self.latency_warn_ms:
                warnings.append(f"healthz latency {health['latency_ms']}ms > {self.latency_warn_ms}ms")

        if self.prom_url:
            prom = await asyncio.to_thread(fetch_url, self.prom_url, self.http_timeout_sec)
            prom_value = parse_prom_metric_value(prom.get("body", ""), self.prom_match) if prom["ok"] else None
            data["prom_up"] = {
                "url": self.prom_url,
                "match": self.prom_match,
                "value": prom_value,
                "min_value": self.prom_min_value,
                "status_code": prom.get("status_code"),
                "latency_ms": prom.get("latency_ms"),
            }
            if not prom["ok"]:
                failures.append(f"prom scrape failed ({prom.get('error', 'unknown')})")
            elif prom_value is None:
                failures.append(f"prom signal not found: {self.prom_match}")
            elif prom_value < self.prom_min_value:
                failures.append(f"prom signal below threshold: {prom_value} < {self.prom_min_value}")

            if self.latency_warn_ms > 0 and prom.get("latency_ms", 0) > self.latency_warn_ms:
                warnings.append(f"prom latency {prom['latency_ms']}ms > {self.latency_warn_ms}ms")

        if failures:
            return {"status": "critical", "message": "; ".join(failures), "data": data}
        if warnings:
            return {"status": "warn", "message": "; ".join(warnings), "data": data}
        return {"status": "ok", "data": data}


def build_modules(config: dict) -> list[MaintainerModule]:
    modules: dict[str, MaintainerModule] = {
        "process": ProcessModule(interval=config["process"]["interval"]),
        "gpu": GPUModule(
            interval=config["gpu"]["interval"],
            temp_warn=config["gpu"]["temp_warn"],
            temp_crit=config["gpu"]["temp_crit"],
        ),
        "memory": MemoryModule(
            interval=config["memory"]["interval"],
            ram_warn=config["memory"]["ram_warn"],
            swap_crit=config["memory"]["swap_crit"],
        ),
        "disk": DiskModule(
            interval=config["disk"]["interval"],
            path=config["disk"]["path"],
            warn_pct=config["disk"]["warn_pct"],
            crit_pct=config["disk"]["crit_pct"],
        ),
        "config_drift": ConfigDriftModule(interval=config["config_drift"]["interval"]),
        "sentinel_probe": SentinelProbeModule(
            interval=config["sentinel_probe"]["interval"],
            health_url=config["sentinel_probe"]["health_url"],
            prom_url=config["sentinel_probe"]["prom_url"],
            prom_match=config["sentinel_probe"]["prom_match"],
            prom_min_value=float(config["sentinel_probe"]["prom_min_value"]),
            latency_warn_ms=float(config["sentinel_probe"]["latency_warn_ms"]),
            http_timeout_sec=float(config["sentinel_probe"]["http_timeout_sec"]),
        ),
    }
    return [modules[name] for name in config["enabled_modules"]]


async def remediate_process_restart(reason: str) -> None:
    action = "process_restart"
    action_state = get_remediation_state(action)
    ts_now = now()

    window_start = action_state.get("window_start_ts", ts_now)
    retry_count = action_state.get("retry_count", 0)
    last_attempt_ts = action_state.get("last_attempt_ts", 0)

    if ts_now - window_start >= PROCESS_RESTART_RETRY_WINDOW_SEC:
        window_start = ts_now
        retry_count = 0

    since_last_attempt = ts_now - last_attempt_ts
    if last_attempt_ts and since_last_attempt < PROCESS_RESTART_COOLDOWN_SEC:
        remaining = PROCESS_RESTART_COOLDOWN_SEC - since_last_attempt
        action_state.update(
            {
                "window_start_ts": window_start,
                "retry_count": retry_count,
                "last_action": "cooldown_skip",
                "last_reason": reason,
                "cooldown_remaining_sec": remaining,
                "updated_ts": ts_now,
            }
        )
        save_remediation_state(action, action_state)
        log("remediation", "skipped", f"Restart cooldown active ({remaining}s remaining)")
        return

    if retry_count >= PROCESS_RESTART_MAX_RETRIES:
        action_state.update(
            {
                "window_start_ts": window_start,
                "retry_count": retry_count,
                "last_action": "retry_cap_skip",
                "last_reason": reason,
                "updated_ts": ts_now,
            }
        )
        save_remediation_state(action, action_state)
        log(
            "remediation",
            "blocked",
            f"Restart retry cap reached ({retry_count}/{PROCESS_RESTART_MAX_RETRIES})",
        )
        return

    cmd = ["systemctl", "restart", SERVICE_NAME]
    if REMEDIATION_DRY_RUN:
        log("remediation", "dry_run", f"Would run: {' '.join(cmd)}")
        action_name = "dry_run_restart"
    else:
        log("remediation", "action", f"Restarting {SERVICE_NAME}")
        subprocess.run(cmd, check=False)
        action_name = "restart"

    retry_count += 1
    action_state.update(
        {
            "window_start_ts": window_start,
            "retry_count": retry_count,
            "last_attempt_ts": ts_now,
            "last_action": action_name,
            "last_reason": reason,
            "cooldown_remaining_sec": 0,
            "updated_ts": ts_now,
            "dry_run": REMEDIATION_DRY_RUN,
            "cooldown_sec": PROCESS_RESTART_COOLDOWN_SEC,
            "max_retries": PROCESS_RESTART_MAX_RETRIES,
            "retry_window_sec": PROCESS_RESTART_RETRY_WINDOW_SEC,
        }
    )
    save_remediation_state(action, action_state)


async def remediate(module_name: str, result: dict) -> None:
    if result.get("status") != "critical":
        return
    if module_name == "process":
        await remediate_process_restart(result.get("message", "process critical"))


async def scheduler(modules: list[MaintainerModule]) -> None:
    last_run_ts = {module.name: 0 for module in modules}
    while True:
        for module in modules:
            since_last = now() - last_run_ts[module.name]
            if since_last >= module.interval:
                try:
                    result = await asyncio.wait_for(module.run(), timeout=module.interval)
                except asyncio.TimeoutError:
                    result = {"status": "error", "message": "Module timeout"}
                except Exception as exc:  # noqa: BLE001
                    result = {"status": "error", "message": str(exc)}

                log(module.name, result["status"], result.get("message", ""), result.get("data"))
                dispatch_alert(module.name, result)
                record_module_state(module.name, result)
                await remediate(module.name, result)
                last_run_ts[module.name] = now()
        await asyncio.sleep(LOOP_SLEEP_SECONDS)


async def main() -> None:
    config = load_config()
    apply_config(config)
    modules = build_modules(config)
    print("Maintainer starting...")
    await scheduler(modules)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Configuration error: {exc}")
        raise SystemExit(2)
