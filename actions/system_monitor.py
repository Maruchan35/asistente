"""system_monitor.py — Full system monitoring: CPU, RAM, GPU, disk, network,
temperature, battery, uptime, processes, and kill by name/PID."""
from __future__ import annotations
import os, subprocess, time
import psutil

def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (r.stdout or "").strip()
    except Exception as e:
        return f"ERROR: {e}"

def _gpu_info() -> str:
    """Get GPU name + VRAM via WMI."""
    try:
        out = _ps("Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1")
        if out and "ERROR" not in out:
            lines = []
            for row in out.splitlines()[:2]:
                parts = [p.strip('"') for p in row.split(',')]
                if len(parts) >= 2:
                    name = parts[0]
                    try:
                        ram_gb = int(parts[1]) / (1024**3)
                        lines.append(f"{name} ({ram_gb:.1f} GB VRAM)")
                    except Exception:
                        lines.append(name)
            return " | ".join(lines) if lines else "GPU: no info"
    except Exception:
        pass
    return "GPU: no disponible"

def _temps() -> str:
    """Read CPU temperatures via Open Hardware Monitor WMI or psutil."""
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            all_t = []
            for sensor_name, entries in temps.items():
                for e in entries:
                    if e.current and e.current > 0:
                        all_t.append(f"{sensor_name}: {e.current:.0f}°C")
            if all_t:
                return " | ".join(all_t[:4])
    except Exception:
        pass
    # Fallback: WMI Open Hardware Monitor
    out = _ps("Get-WmiObject -Namespace root/OpenHardwareMonitor -Class Sensor -Filter \"SensorType='Temperature'\" | Select-Object Name,Value | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1 -First 4")
    if out and "ERROR" not in out:
        lines = []
        for row in out.splitlines():
            parts = [p.strip('"') for p in row.split(',')]
            if len(parts) == 2:
                try: lines.append(f"{parts[0]}: {float(parts[1]):.0f}°C")
                except Exception: pass
        if lines: return " | ".join(lines)
    return "Temperatura: no disponible (instala Open Hardware Monitor para monitoreo térmico)"

# ══════════════════════════════════════════════════════════════════════════════
def system_monitor(parameters: dict = None, player=None) -> str:
    parameters = parameters or {}
    action  = parameters.get("action", "report").lower().strip()
    sort_by = parameters.get("sort_by", "cpu").lower()
    count   = int(parameters.get("count", 10))
    name    = parameters.get("name", "").strip()

    def log(msg):
        if player: player.write_log(f"💻 {msg[:120]}")

    # ── CPU ──────────────────────────────────────────────────────────────────
    if action == "cpu":
        cpu = psutil.cpu_percent(interval=0.5)
        freq = psutil.cpu_freq()
        cores = psutil.cpu_count(logical=False)
        threads = psutil.cpu_count(logical=True)
        freq_str = f" @ {freq.current:.0f} MHz" if freq else ""
        msg = f"CPU: {cpu}% de uso | {cores} núcleos / {threads} hilos{freq_str}"
        log(msg); return msg

    # ── RAM ──────────────────────────────────────────────────────────────────
    elif action == "ram":
        vm = psutil.virtual_memory()
        used  = vm.used  / (1024**3)
        total = vm.total / (1024**3)
        avail = vm.available / (1024**3)
        msg = f"RAM: {vm.percent}% usada — {used:.1f} GB / {total:.1f} GB (disponible: {avail:.1f} GB)"
        log(msg); return msg

    # ── DISK ─────────────────────────────────────────────────────────────────
    elif action == "disk":
        lines = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                used  = usage.used  / (1024**3)
                total = usage.total / (1024**3)
                free  = usage.free  / (1024**3)
                lines.append(
                    f"{part.device} ({part.mountpoint}): "
                    f"{usage.percent}% — {used:.1f}/{total:.1f} GB (libre: {free:.1f} GB)"
                )
            except Exception:
                pass
        msg = "\n".join(lines) if lines else "No se pudieron leer los discos."
        log(msg); return msg

    # ── NETWORK ──────────────────────────────────────────────────────────────
    elif action == "network":
        stats = psutil.net_io_counters()
        sent  = stats.bytes_sent  / (1024**2)
        recv  = stats.bytes_recv  / (1024**2)
        # Per-interface
        ifaces = []
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == 2:  # IPv4
                    ifaces.append(f"{iface}: {addr.address}")
        iface_str = " | ".join(ifaces[:3])
        msg = f"Red — Enviados: {sent:.1f} MB | Recibidos: {recv:.1f} MB\nInterfaces: {iface_str}"
        log(msg); return msg

    # ── GPU ──────────────────────────────────────────────────────────────────
    elif action == "gpu":
        msg = _gpu_info()
        log(msg); return msg

    # ── TEMPERATURE ──────────────────────────────────────────────────────────
    elif action in ("temperature", "temp", "temperatura"):
        msg = _temps()
        log(msg); return msg

    # ── BATTERY ──────────────────────────────────────────────────────────────
    elif action == "battery":
        try:
            bat = psutil.sensors_battery()
            if bat:
                status = "cargando" if bat.power_plugged else "descargando"
                secs   = bat.secsleft
                time_str = f" — {secs//3600}h {(secs%3600)//60}m restantes" if secs > 0 and not bat.power_plugged else ""
                msg = f"Batería: {bat.percent:.0f}% ({status}){time_str}"
            else:
                msg = "Sin batería detectada (PC de escritorio)."
        except Exception as e:
            msg = f"Error leyendo batería: {e}"
        log(msg); return msg

    # ── UPTIME ────────────────────────────────────────────────────────────────
    elif action == "uptime":
        boot = psutil.boot_time()
        elapsed = time.time() - boot
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        msg = f"Sistema encendido hace: {h}h {m}m"
        log(msg); return msg

    # ── PROCESSES ────────────────────────────────────────────────────────────
    elif action == "processes":
        procs = []
        for p in psutil.process_iter(["pid","name","cpu_percent","memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        key = "memory_percent" if sort_by == "ram" else "cpu_percent"
        procs.sort(key=lambda x: x.get(key, 0) or 0, reverse=True)
        lines = []
        for p in procs[:count]:
            cpu = p.get("cpu_percent", 0) or 0
            mem = p.get("memory_percent", 0) or 0
            lines.append(f"[{p['pid']:>6}] {p['name']:<30} CPU:{cpu:>5.1f}%  RAM:{mem:>4.1f}%")
        msg = f"Top {count} procesos (ordenado por {sort_by}):\n" + "\n".join(lines)
        log(msg); return msg

    # ── KILL ─────────────────────────────────────────────────────────────────
    elif action == "kill":
        if not name:
            return "Especificá el nombre o PID del proceso a terminar."
        killed = []
        errors = []
        # Try by PID first
        if name.isdigit():
            try:
                p = psutil.Process(int(name))
                pname = p.name()
                p.terminate()
                killed.append(f"PID {name} ({pname})")
            except Exception as e:
                errors.append(str(e))
        else:
            # Kill by name (all matching)
            for p in psutil.process_iter(["pid","name"]):
                try:
                    if name.lower() in p.info["name"].lower():
                        p.terminate()
                        killed.append(f"{p.info['name']} (PID {p.info['pid']})")
                except Exception as e:
                    errors.append(str(e))
        if killed:
            msg = f"Proceso(s) terminado(s): {', '.join(killed)}"
        elif errors:
            msg = f"No se pudo terminar '{name}': {errors[0]}"
        else:
            msg = f"No se encontró ningún proceso llamado '{name}'."
        log(msg); return msg

    # ── FULL REPORT ──────────────────────────────────────────────────────────
    elif action in ("report", "all", "todo", "resumen"):
        cpu  = psutil.cpu_percent(interval=0.5)
        vm   = psutil.virtual_memory()
        used = vm.used  / (1024**3)
        tot  = vm.total / (1024**3)

        # Disk (C: or first partition)
        disk_str = "N/A"
        for part in psutil.disk_partitions():
            try:
                du = psutil.disk_usage(part.mountpoint)
                disk_str = f"{du.percent}% ({du.free/(1024**3):.1f} GB libre)"
                break
            except Exception:
                pass

        # Battery
        bat_str = "N/A"
        try:
            bat = psutil.sensors_battery()
            if bat:
                bat_str = f"{bat.percent:.0f}% ({'cargando' if bat.power_plugged else 'descargando'})"
        except Exception:
            pass

        # Network
        net = psutil.net_io_counters()
        net_str = f"↑{net.bytes_sent/(1024**2):.0f} MB  ↓{net.bytes_recv/(1024**2):.0f} MB"

        # Uptime
        elapsed = time.time() - psutil.boot_time()
        uptime  = f"{int(elapsed//3600)}h {int((elapsed%3600)//60)}m"

        gpu = _gpu_info()

        lines = [
            f"CPU:      {cpu}% de uso",
            f"RAM:      {vm.percent}% — {used:.1f}/{tot:.1f} GB",
            f"Disco:    {disk_str}",
            f"GPU:      {gpu}",
            f"Red:      {net_str}",
            f"Batería:  {bat_str}",
            f"Encendida: {uptime}",
        ]
        msg = "\n".join(lines)
        log("Reporte completo generado"); return msg

    return f"Acción '{action}' no reconocida. Usa: cpu | ram | disk | network | gpu | temperature | battery | uptime | processes | kill | report"
