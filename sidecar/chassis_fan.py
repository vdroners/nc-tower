"""Chassis PWM fan control for NC Tower.

Ports the Webmin fan-control module (nct6796 / ASUS X299) into the sidecar:
per-header names/roles, PWM modes, 5-point curves, named profiles, pump
safety, fancontrol.service conflict detection, reboot-survival config, and a
30 s trend sampler for the Ops charts.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

# Webmin fan-control profile_curves (silent/balanced/performance), temps °C.
PROFILE_CURVES: dict[str, dict[str, dict[str, list[int]]]] = {
    "silent": {
        "radiator": {"temps": [30, 50, 65, 75, 85], "pwms": [102, 140, 204, 255, 255]},
        "case": {"temps": [30, 50, 65, 75, 85], "pwms": [76, 115, 178, 255, 255]},
    },
    "balanced": {
        "radiator": {"temps": [25, 45, 60, 70, 80], "pwms": [127, 166, 229, 255, 255]},
        "case": {"temps": [25, 45, 60, 70, 80], "pwms": [102, 140, 204, 255, 255]},
    },
    "performance": {
        "radiator": {"temps": [20, 40, 55, 65, 75], "pwms": [178, 217, 255, 255, 255]},
        "case": {"temps": [20, 40, 55, 65, 75], "pwms": [153, 191, 255, 255, 255]},
    },
}

# Quiet / normal aliases used in the plan map onto Webmin names.
PROFILE_ALIASES = {
    "quiet": "silent",
    "normal": "balanced",
    "silent": "silent",
    "balanced": "balanced",
    "performance": "performance",
}

DEFAULT_HEADERS = {
    1: "CPU_FAN",
    2: "CHA_FAN1",
    3: "CHA_FAN2",
    4: "CHA_FAN3",
    5: "AIO_PUMP",
    6: "EXT_FAN",
    7: "W_PUMP+",
}

DEFAULT_ROLES = {
    1: "radiator",
    2: "radiator",
    3: "unused",
    4: "unused",
    5: "unused",
    6: "unused",
    7: "pump",
}

PWM_MODE_LABELS = {
    0: "Off (DANGER)",
    1: "Manual",
    2: "Thermal Cruise",
    3: "Speed Cruise",
    4: "SmartFan IV",
    5: "Automatic (BIOS)",
}

ALLOWED_MODES = {1, 2, 5}
VALID_ROLES = {"pump", "radiator", "case", "unused"}
CHIP_HINTS = ("nct6796", "nct6775", "nct6776", "nct6779")


def validate_curve(points: list[Any]) -> tuple[list[tuple[int, int]] | None, str | None]:
    """Validate five [temp_c, pwm] points: monotonic temps, pwm in 0..255."""
    if not isinstance(points, list) or len(points) != 5:
        return None, "curve_requires_5_points"
    parsed: list[tuple[int, int]] = []
    prev_temp = -1
    for item in points:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return None, "curve_point_must_be_temp_pwm_pair"
        try:
            temp = int(item[0])
            pwm = int(item[1])
        except (TypeError, ValueError):
            return None, "curve_point_not_int"
        if not 0 <= temp <= 120:
            return None, "temp_out_of_range"
        if not 0 <= pwm <= 255:
            return None, "pwm_out_of_range"
        if temp < prev_temp:
            return None, "temps_must_be_monotonic"
        prev_temp = temp
        parsed.append((temp, pwm))
    return parsed, None


def validate_rename(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name or ""))


class ChassisFanController:
    """Stateful chassis fan controller bound to an OPS_ROOT and helpers."""

    def __init__(
        self,
        ops_root: Path,
        *,
        read_text: Callable[[Path], str],
        number: Callable[[str], float | int | None],
        run: Callable[..., dict[str, Any]],
        nsenter_bin: Callable[[], str | None],
        audit: Callable[[str], None],
        fan_set: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        gpu_status: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.ops_root = Path(ops_root)
        self.state_dir = self.ops_root / "state"
        self.config_path = self.state_dir / "fan-config.json"
        self.trend_path = self.state_dir / "fan-trend.jsonl"
        self._read_text = read_text
        self._number = number
        self._run = run
        self._nsenter_bin = nsenter_bin
        self._audit = audit
        self._fan_set = fan_set
        self._gpu_status = gpu_status
        self._lock = threading.Lock()
        self._ring: deque[dict[str, Any]] = deque(maxlen=2880)  # ~24h @ 30s
        self._sampler_stop = threading.Event()
        self._sampler_thread: threading.Thread | None = None

    # ---- config persistence -------------------------------------------------

    def _default_config(self) -> dict[str, Any]:
        return {
            "headers": {str(k): v for k, v in DEFAULT_HEADERS.items()},
            "roles": {str(k): v for k, v in DEFAULT_ROLES.items()},
            "active_profile": None,
            "per_header": {},
        }

    def load_config(self) -> dict[str, Any]:
        cfg = self._default_config()
        if self.config_path.is_file():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    cfg.update({k: raw[k] for k in cfg if k in raw})
                    if isinstance(raw.get("headers"), dict):
                        cfg["headers"] = {**cfg["headers"], **{str(k): str(v) for k, v in raw["headers"].items()}}
                    if isinstance(raw.get("roles"), dict):
                        cfg["roles"] = {
                            **cfg["roles"],
                            **{str(k): str(v) for k, v in raw["roles"].items() if str(v) in VALID_ROLES},
                        }
                    if isinstance(raw.get("per_header"), dict):
                        cfg["per_header"] = raw["per_header"]
                    if raw.get("active_profile") in PROFILE_CURVES or raw.get("active_profile") in PROFILE_ALIASES:
                        cfg["active_profile"] = PROFILE_ALIASES.get(
                            str(raw["active_profile"]), raw.get("active_profile")
                        )
            except (OSError, json.JSONDecodeError):
                pass
        # Seed from Webmin config when present and ours is still defaults-only.
        self._seed_from_webmin(cfg)
        return cfg

    def _seed_from_webmin(self, cfg: dict[str, Any]) -> None:
        webmin = Path("/etc/webmin/fan-control/config")
        if not webmin.is_file():
            return
        try:
            text = webmin.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for line in text.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            m = re.fullmatch(r"fan(\d+)_header", key)
            if m:
                cfg["headers"][m.group(1)] = value
            m = re.fullmatch(r"fan(\d+)_role", key)
            if m and value in VALID_ROLES:
                cfg["roles"][m.group(1)] = value
            if key == "active_profile" and value in PROFILE_CURVES:
                if not cfg.get("active_profile"):
                    cfg["active_profile"] = value

    def save_config(self, cfg: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.config_path)

    # ---- sysfs helpers ------------------------------------------------------

    def _find_chip(self) -> Path | None:
        for base in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
            name = self._read_text(base / "name").strip().lower()
            if any(hint in name for hint in CHIP_HINTS):
                return base
        # Fallback: first chip with pwm*_enable
        for base in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
            if any(base.glob("pwm*_enable")):
                return base
        return None

    def _sysfs_write(self, path: Path, value: str | int) -> bool:
        """Write via nsenter when available so containerized sidecar reaches host sysfs."""
        nsenter = self._nsenter_bin()
        text = str(value)
        if nsenter and Path("/proc/1/ns/mnt").exists():
            result = self._run(
                [
                    nsenter,
                    "--mount=/proc/1/ns/mnt",
                    "--",
                    "/bin/sh",
                    "-c",
                    f"printf %s {json.dumps(text)} | tee {path} >/dev/null",
                ],
                timeout=5,
            )
            return result.get("exit") == 0
        try:
            path.write_text(text, encoding="utf-8")
            return True
        except OSError:
            return False

    def _sysfs_read(self, path: Path) -> str:
        nsenter = self._nsenter_bin()
        if nsenter and Path("/proc/1/ns/mnt").exists() and not path.is_file():
            result = self._run(
                [nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/cat", str(path)],
                timeout=5,
            )
            if result.get("exit") == 0:
                return result.get("stdout") or ""
        return self._read_text(path)

    def _fancontrol_managed(self) -> set[str]:
        """Return set of pwm names (pwm2, …) claimed by /etc/fancontrol."""
        managed: set[str] = set()
        path = Path("/etc/fancontrol")
        text = ""
        if path.is_file():
            text = self._read_text(path)
        else:
            nsenter = self._nsenter_bin()
            if nsenter:
                result = self._run(
                    [nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/cat", "/etc/fancontrol"],
                    timeout=5,
                )
                text = result.get("stdout") or ""
        for match in re.finditer(r"/(pwm\d+)=", text):
            managed.add(match.group(1))
        return managed

    def _fancontrol_active(self) -> bool:
        nsenter = self._nsenter_bin()
        argv = ["systemctl", "is-active", "fancontrol.service"]
        if nsenter:
            argv = [nsenter, "--mount=/proc/1/ns/mnt", "--", "/bin/systemctl", "is-active", "fancontrol.service"]
        result = self._run(argv, timeout=5)
        return (result.get("stdout") or "").strip() == "active"

    # ---- read path ----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        cfg = self.load_config()
        chip = self._find_chip()
        managed = self._fancontrol_managed() if self._fancontrol_active() else set()
        fans: list[dict[str, Any]] = []
        temps: list[dict[str, Any]] = []
        chips: list[dict[str, Any]] = []

        for base in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
            chip_name = self._read_text(base / "name").strip()
            chip_fans: list[dict[str, Any]] = []
            for source in sorted(base.glob("fan*_input")):
                token = source.stem.split("_")[0]
                m = re.match(r"fan(\d+)", token)
                idx = int(m.group(1)) if m else 0
                pwm_path = base / f"pwm{idx}"
                enable_path = base / f"pwm{idx}_enable"
                curve = []
                for pt in range(1, 6):
                    t_path = base / f"pwm{idx}_auto_point{pt}_temp"
                    p_path = base / f"pwm{idx}_auto_point{pt}_pwm"
                    if t_path.is_file() and p_path.is_file():
                        temp_milli = self._number(self._read_text(t_path))
                        pwm_val = self._number(self._read_text(p_path))
                        curve.append(
                            {
                                "temp_c": (temp_milli / 1000.0) if isinstance(temp_milli, (int, float)) else None,
                                "pwm": pwm_val,
                            }
                        )
                mode = self._number(self._read_text(enable_path)) if enable_path.is_file() else None
                role = cfg["roles"].get(str(idx), "unused")
                header = cfg["headers"].get(str(idx), f"FAN{idx}")
                pwm_name = f"pwm{idx}"
                entry = {
                    "index": idx,
                    "fan": token,
                    "header": header,
                    "name": header,
                    "role": role,
                    "rpm": self._number(self._read_text(source)),
                    "label": self._read_text(base / f"{token}_label").strip() or None,
                    "pwm": self._number(self._read_text(pwm_path)) if pwm_path.is_file() else None,
                    "pwm_pct": None,
                    "mode": int(mode) if isinstance(mode, (int, float)) else None,
                    "mode_label": PWM_MODE_LABELS.get(int(mode), "unknown") if isinstance(mode, (int, float)) else None,
                    "curve": curve,
                    "chip": chip_name,
                    "hwmon": base.name,
                    "fancontrol_managed": pwm_name in managed,
                    "min_rpm": self._number(self._read_text(base / f"{token}_min")),
                    "max_rpm": self._number(self._read_text(base / f"{token}_max")),
                }
                if isinstance(entry["pwm"], (int, float)):
                    entry["pwm_pct"] = round(float(entry["pwm"]) * 100.0 / 255.0, 1)
                chip_fans.append(entry)
                fans.append(entry)

            chip_temps = []
            for source in sorted(base.glob("temp*_input")):
                token = source.stem.split("_")[0]
                milli = self._number(self._read_text(source))
                chip_temps.append(
                    {
                        "temp": token,
                        "label": self._read_text(base / f"{token}_label").strip() or f"{chip_name}:{token}",
                        "celsius": (milli / 1000.0) if isinstance(milli, (int, float)) else None,
                        "chip": chip_name,
                        "hwmon": base.name,
                    }
                )
            temps.extend(chip_temps)

            pwms = [
                {
                    "pwm": source.name,
                    "value": self._number(self._read_text(source)),
                    "enable": self._number(self._read_text(base / f"{source.name}_enable")),
                    "fancontrol_managed": source.name in managed,
                }
                for source in sorted(base.glob("pwm[0-9]*"))
                if re.fullmatch(r"pwm\d+", source.name)
            ]
            if chip_fans or pwms or chip_temps:
                chips.append(
                    {
                        "hwmon": base.name,
                        "name": chip_name,
                        "fans": chip_fans,
                        "pwms": pwms,
                        "temps": chip_temps,
                        "primary": chip is not None and base == chip,
                    }
                )

        warnings = []
        if managed and self._fancontrol_active():
            warnings.append(
                f"fancontrol.service is active and manages {', '.join(sorted(managed))}; "
                "Tower writes to those PWMs may be overwritten."
            )
        return {
            "chips": chips,
            "fans": fans,
            "items": fans,
            "temps": temps,
            "active_profile": cfg.get("active_profile"),
            "headers": cfg.get("headers"),
            "roles": cfg.get("roles"),
            "profiles": list(PROFILE_CURVES.keys()),
            "fancontrol_active": self._fancontrol_active(),
            "fancontrol_managed": sorted(managed),
            "warnings": warnings,
            "ts": time.time(),
        }

    # ---- pump safety --------------------------------------------------------

    def _ensure_pump_safety(self, cfg: dict[str, Any] | None = None) -> None:
        cfg = cfg or self.load_config()
        chip = self._find_chip()
        if chip is None:
            return
        for idx_s, role in cfg.get("roles", {}).items():
            if role != "pump":
                continue
            idx = int(idx_s)
            enable = chip / f"pwm{idx}_enable"
            value = chip / f"pwm{idx}"
            if value.is_file():
                current = self._number(self._read_text(value))
                if not isinstance(current, (int, float)) or current < 255:
                    if enable.is_file():
                        self._sysfs_write(enable, 1)
                    self._sysfs_write(value, 255)

    def _role_for(self, header: int, cfg: dict[str, Any] | None = None) -> str:
        cfg = cfg or self.load_config()
        return str(cfg.get("roles", {}).get(str(header), "unused"))

    # ---- mutate ops ---------------------------------------------------------

    def mutate(self, body: dict[str, Any]) -> dict[str, Any]:
        op = str(body.get("op") or "")
        with self._lock:
            if op == "set-mode":
                return self._set_mode(body)
            if op == "set-value":
                return self._set_value(body)
            if op == "set-curve":
                return self._set_curve(body)
            if op == "apply-profile":
                return self._apply_profile(body)
            if op == "set-config":
                return self._set_config(body)
            if op == "restore-bios-defaults":
                return self._restore_bios()
            if op == "re-apply":
                return self.re_apply()
            return {"ok": False, "error": "invalid_op", "http": 400}

    def _chip_or_fail(self) -> tuple[Path | None, dict[str, Any] | None]:
        chip = self._find_chip()
        if chip is None:
            return None, {"ok": False, "error": "hwmon_chip_missing", "http": 503}
        return chip, None

    def _header_index(self, body: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
        try:
            header = int(body.get("header", body.get("fan", -1)))
        except (TypeError, ValueError):
            return None, {"ok": False, "error": "invalid_header", "http": 400}
        if not 1 <= header <= 7:
            return None, {"ok": False, "error": "header_out_of_range", "http": 400}
        return header, None

    def _set_mode(self, body: dict[str, Any]) -> dict[str, Any]:
        header, err = self._header_index(body)
        if err:
            return err
        try:
            mode = int(body.get("mode"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_mode", "http": 400}
        if mode == 0:
            return {"ok": False, "error": "mode_0_forbidden", "http": 400}
        if mode not in ALLOWED_MODES:
            return {"ok": False, "error": "mode_not_allowed", "http": 400}
        cfg = self.load_config()
        if self._role_for(header, cfg) == "pump" and mode != 1:
            return {"ok": False, "error": "pump_must_stay_manual_full", "http": 400}
        chip, err = self._chip_or_fail()
        if err:
            return err
        assert chip is not None and header is not None
        ok = self._sysfs_write(chip / f"pwm{header}_enable", mode)
        if self._role_for(header, cfg) == "pump":
            self._sysfs_write(chip / f"pwm{header}", 255)
        self._ensure_pump_safety(cfg)
        cfg["active_profile"] = None
        cfg.setdefault("per_header", {})[str(header)] = {"mode": mode}
        self.save_config(cfg)
        self._audit(f"chassis-fan set-mode header={header} mode={mode} ok={ok}")
        return {"ok": ok, "op": "set-mode", "header": header, "mode": mode}

    def _set_value(self, body: dict[str, Any]) -> dict[str, Any]:
        header, err = self._header_index(body)
        if err:
            return err
        cfg = self.load_config()
        if self._role_for(header, cfg) == "pump":
            return {"ok": False, "error": "pump_value_locked", "http": 400}
        try:
            if "pwm" in body and body["pwm"] is not None:
                pwm = int(body["pwm"])
            elif "pct" in body and body["pct"] is not None:
                pwm = int(round(float(body["pct"]) * 255.0 / 100.0))
            elif "speed" in body and body["speed"] is not None:
                pwm = int(round(float(body["speed"]) * 255.0 / 100.0))
            else:
                return {"ok": False, "error": "pwm_or_pct_required", "http": 400}
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_pwm", "http": 400}
        if not 0 <= pwm <= 255:
            return {"ok": False, "error": "pwm_out_of_range", "http": 400}
        chip, err = self._chip_or_fail()
        if err:
            return err
        assert chip is not None and header is not None
        enable_path = chip / f"pwm{header}_enable"
        current_mode = self._number(self._read_text(enable_path)) if enable_path.is_file() else None
        if current_mode != 1:
            self._sysfs_write(enable_path, 1)
        ok = self._sysfs_write(chip / f"pwm{header}", pwm)
        self._ensure_pump_safety(cfg)
        cfg["active_profile"] = None
        cfg.setdefault("per_header", {})[str(header)] = {"mode": 1, "pwm": pwm}
        self.save_config(cfg)
        self._audit(f"chassis-fan set-value header={header} pwm={pwm} ok={ok}")
        return {"ok": ok, "op": "set-value", "header": header, "pwm": pwm}

    def _set_curve(self, body: dict[str, Any]) -> dict[str, Any]:
        header, err = self._header_index(body)
        if err:
            return err
        cfg = self.load_config()
        if self._role_for(header, cfg) == "pump":
            return {"ok": False, "error": "pump_curve_locked", "http": 400}
        points, cerr = validate_curve(body.get("points") or [])
        if cerr or points is None:
            return {"ok": False, "error": cerr, "http": 400}
        chip, err = self._chip_or_fail()
        if err:
            return err
        assert chip is not None and header is not None
        ok = True
        for i, (temp, pwm) in enumerate(points, start=1):
            t_path = chip / f"pwm{header}_auto_point{i}_temp"
            p_path = chip / f"pwm{header}_auto_point{i}_pwm"
            if t_path.is_file():
                ok = self._sysfs_write(t_path, int(temp * 1000)) and ok
            if p_path.is_file():
                ok = self._sysfs_write(p_path, pwm) and ok
        ok = self._sysfs_write(chip / f"pwm{header}_enable", 5) and ok
        self._ensure_pump_safety(cfg)
        cfg["active_profile"] = None
        cfg.setdefault("per_header", {})[str(header)] = {
            "mode": 5,
            "curve": [{"temp_c": t, "pwm": p} for t, p in points],
        }
        self.save_config(cfg)
        self._audit(f"chassis-fan set-curve header={header} ok={ok}")
        return {"ok": ok, "op": "set-curve", "header": header, "points": points}

    def _apply_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        name = str(body.get("profile") or body.get("name") or "")
        resolved = PROFILE_ALIASES.get(name)
        if not resolved or resolved not in PROFILE_CURVES:
            return {"ok": False, "error": "unknown_profile", "http": 400}
        curves = PROFILE_CURVES[resolved]
        cfg = self.load_config()
        chip, err = self._chip_or_fail()
        if err:
            return err
        assert chip is not None
        ok = True
        for idx in range(1, 8):
            role = self._role_for(idx, cfg)
            enable = chip / f"pwm{idx}_enable"
            if not enable.is_file():
                continue
            if role == "pump":
                self._sysfs_write(enable, 1)
                ok = self._sysfs_write(chip / f"pwm{idx}", 255) and ok
                continue
            if role == "unused":
                continue
            curve = curves.get(role) or curves.get("case")
            if not curve:
                continue
            temps = curve["temps"]
            pwms = curve["pwms"]
            for pt in range(5):
                t_path = chip / f"pwm{idx}_auto_point{pt + 1}_temp"
                p_path = chip / f"pwm{idx}_auto_point{pt + 1}_pwm"
                if t_path.is_file():
                    ok = self._sysfs_write(t_path, temps[pt] * 1000) and ok
                if p_path.is_file():
                    ok = self._sysfs_write(p_path, pwms[pt]) and ok
            ok = self._sysfs_write(enable, 5) and ok
        if resolved == "performance" and self._fan_set:
            self._fan_set({"op": "set-all-speeds", "speed": 80})
        elif self._fan_set:
            self._fan_set({"op": "set-auto"})
        self._ensure_pump_safety(cfg)
        cfg["active_profile"] = resolved
        cfg["per_header"] = {}
        self.save_config(cfg)
        self._audit(f"chassis-fan apply-profile profile={resolved} ok={ok}")
        return {"ok": ok, "op": "apply-profile", "profile": resolved}

    def _set_config(self, body: dict[str, Any]) -> dict[str, Any]:
        cfg = self.load_config()
        headers = body.get("headers")
        roles = body.get("roles")
        if isinstance(headers, dict):
            for key, value in headers.items():
                if re.fullmatch(r"[1-7]", str(key)) and isinstance(value, str) and 1 <= len(value) <= 32:
                    cfg["headers"][str(key)] = value
        if isinstance(roles, dict):
            for key, value in roles.items():
                if re.fullmatch(r"[1-7]", str(key)) and str(value) in VALID_ROLES:
                    cfg["roles"][str(key)] = str(value)
        self.save_config(cfg)
        self._ensure_pump_safety(cfg)
        self._audit("chassis-fan set-config")
        return {"ok": True, "op": "set-config", "headers": cfg["headers"], "roles": cfg["roles"]}

    def _restore_bios(self) -> dict[str, Any]:
        chip, err = self._chip_or_fail()
        if err:
            return err
        assert chip is not None
        cfg = self.load_config()
        ok = True
        for idx in range(1, 8):
            enable = chip / f"pwm{idx}_enable"
            if not enable.is_file():
                continue
            if self._role_for(idx, cfg) == "pump":
                self._sysfs_write(enable, 1)
                ok = self._sysfs_write(chip / f"pwm{idx}", 255) and ok
            else:
                ok = self._sysfs_write(enable, 5) and ok
        self._ensure_pump_safety(cfg)
        cfg["active_profile"] = None
        cfg["per_header"] = {}
        self.save_config(cfg)
        self._audit(f"chassis-fan restore-bios ok={ok}")
        return {"ok": ok, "op": "restore-bios-defaults"}

    def re_apply(self) -> dict[str, Any]:
        """Re-apply saved profile or per-header state after reboot."""
        cfg = self.load_config()
        profile = cfg.get("active_profile")
        if profile in PROFILE_CURVES:
            return self._apply_profile({"profile": profile})
        results = []
        for idx_s, state in (cfg.get("per_header") or {}).items():
            if not isinstance(state, dict):
                continue
            header = int(idx_s)
            if "curve" in state and isinstance(state["curve"], list):
                points = [[p.get("temp_c"), p.get("pwm")] for p in state["curve"]]
                results.append(self._set_curve({"header": header, "points": points}))
            elif state.get("mode") == 1 and "pwm" in state:
                results.append(self._set_value({"header": header, "pwm": state["pwm"]}))
            elif "mode" in state:
                results.append(self._set_mode({"header": header, "mode": state["mode"]}))
        self._ensure_pump_safety(cfg)
        ok = all(r.get("ok") for r in results) if results else True
        self._audit(f"chassis-fan re-apply ok={ok} n={len(results)}")
        return {"ok": ok, "op": "re-apply", "applied": len(results), "results": results}

    # ---- trend sampler ------------------------------------------------------

    def _sample_once(self) -> dict[str, Any]:
        status = self.status()
        gpu = []
        if self._gpu_status:
            try:
                payload = self._gpu_status()
                for row in payload.get("gpus") or payload.get("items") or []:
                    if isinstance(row, dict):
                        gpu.append(
                            {
                                "name": row.get("name"),
                                "temp_c": row.get("temp_c"),
                                "fan_pct": row.get("fan_pct"),
                            }
                        )
            except Exception:  # noqa: BLE001 — sampler must never die
                pass
        sample = {
            "ts": time.time(),
            "fans": [
                {
                    "index": f.get("index"),
                    "header": f.get("header"),
                    "rpm": f.get("rpm"),
                    "pwm": f.get("pwm"),
                    "mode": f.get("mode"),
                    "role": f.get("role"),
                }
                for f in status.get("fans") or []
            ],
            "temps": [
                {"label": t.get("label"), "celsius": t.get("celsius"), "chip": t.get("chip")}
                for t in (status.get("temps") or [])[:12]
            ],
            "gpu": gpu,
            "active_profile": status.get("active_profile"),
        }
        return sample

    def _append_sample(self, sample: dict[str, Any]) -> None:
        self._ring.append(sample)
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with self.trend_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(sample, separators=(",", ":")) + "\n")
            # Rotate if > ~8 MB (~24h of samples is far smaller; hard cap).
            if self.trend_path.stat().st_size > 8_000_000:
                lines = self.trend_path.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
                self.trend_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def history(self, minutes: int = 60) -> dict[str, Any]:
        minutes = max(1, min(int(minutes), 24 * 60))
        cutoff = time.time() - minutes * 60
        samples = [s for s in self._ring if float(s.get("ts") or 0) >= cutoff]
        if len(samples) < 2 and self.trend_path.is_file():
            try:
                for line in self.trend_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and float(row.get("ts") or 0) >= cutoff:
                        samples.append(row)
            except OSError:
                pass
            # Dedup by ts
            by_ts = {float(s["ts"]): s for s in samples if s.get("ts")}
            samples = [by_ts[k] for k in sorted(by_ts)]
        return {"ok": True, "minutes": minutes, "samples": samples, "ts": time.time()}

    def _sampler_loop(self) -> None:
        while not self._sampler_stop.wait(30):
            try:
                self._append_sample(self._sample_once())
            except Exception as exc:  # noqa: BLE001
                self._audit(f"chassis-fan sampler error={exc}")

    def start_sampler(self) -> None:
        if self._sampler_thread and self._sampler_thread.is_alive():
            return
        # Seed ring from disk
        if self.trend_path.is_file():
            try:
                for line in self.trend_path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and row.get("ts"):
                        self._ring.append(row)
            except OSError:
                pass
        self._sampler_stop.clear()
        self._sampler_thread = threading.Thread(target=self._sampler_loop, name="fan-sampler", daemon=True)
        self._sampler_thread.start()
        # Immediate sample so charts aren't empty after restart.
        try:
            self._append_sample(self._sample_once())
        except Exception:  # noqa: BLE001
            pass

    def stop_sampler(self) -> None:
        self._sampler_stop.set()
