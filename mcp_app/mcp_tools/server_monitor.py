"""
mcp_app/mcp_tools/server_monitor.py

Ubuntu server health monitoring tools.
Checks CPU, memory, disk, network traffic, top processes, and service status.
Logs metrics to DB for historical queries.
"""

import json
import subprocess
import psutil
from datetime import datetime, timedelta
from mcp_app.core import mcp
from mcp_app.permission import is_admin
from mcp_app.db import get_connection

_WATCHED_SERVICES = ["uvicorn", "nginx", "mysql", "redis", "php-fpm"]


def _run(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


def _cpu_info() -> dict:
    percent = psutil.cpu_percent(interval=1)
    freq    = psutil.cpu_freq()
    load    = psutil.getloadavg()          # 1m, 5m, 15m
    cores   = psutil.cpu_count(logical=True)

    # Top CPU-consuming processes
    procs = sorted(
        psutil.process_iter(["pid", "name", "cpu_percent", "status"]),
        key=lambda p: p.info["cpu_percent"] or 0,
        reverse=True,
    )[:5]
    top = [{"pid": p.info["pid"], "name": p.info["name"], "cpu": p.info["cpu_percent"]} for p in procs]

    status = "critical" if percent > 90 else "warning" if percent > 70 else "ok"
    return {
        "usage_percent": percent,
        "load_avg":      {"1m": load[0], "5m": load[1], "15m": load[2]},
        "cores":         cores,
        "freq_mhz":      round(freq.current, 1) if freq else None,
        "status":        status,
        "top_processes": top,
    }


def _memory_info() -> dict:
    vm   = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Top memory-consuming processes
    procs = sorted(
        psutil.process_iter(["pid", "name", "memory_percent"]),
        key=lambda p: p.info["memory_percent"] or 0,
        reverse=True,
    )[:5]
    top = [{"pid": p.info["pid"], "name": p.info["name"], "mem_pct": round(p.info["memory_percent"], 1)} for p in procs]

    status = "critical" if vm.percent > 90 else "warning" if vm.percent > 75 else "ok"
    return {
        "total_gb":      round(vm.total / 1e9, 2),
        "used_gb":       round(vm.used / 1e9, 2),
        "available_gb":  round(vm.available / 1e9, 2),
        "usage_percent": vm.percent,
        "swap_used_gb":  round(swap.used / 1e9, 2),
        "swap_percent":  swap.percent,
        "status":        status,
        "top_processes": top,
    }


def _disk_info() -> dict:
    partitions = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            partitions.append({
                "mount":        part.mountpoint,
                "total_gb":     round(usage.total / 1e9, 2),
                "used_gb":      round(usage.used / 1e9, 2),
                "free_gb":      round(usage.free / 1e9, 2),
                "usage_percent": usage.percent,
                "status":       "critical" if usage.percent > 90 else "warning" if usage.percent > 75 else "ok",
            })
        except PermissionError:
            pass
    return {"partitions": partitions}


def _network_info() -> dict:
    net = psutil.net_io_counters()
    conns = psutil.net_connections(kind="inet")
    established = sum(1 for c in conns if c.status == "ESTABLISHED")
    listening   = sum(1 for c in conns if c.status == "LISTEN")
    return {
        "bytes_sent_mb":    round(net.bytes_sent / 1e6, 2),
        "bytes_recv_mb":    round(net.bytes_recv / 1e6, 2),
        "packets_sent":     net.packets_sent,
        "packets_recv":     net.packets_recv,
        "connections":      {"established": established, "listening": listening},
    }


def _services_info() -> list:
    results = []
    for svc in _WATCHED_SERVICES:
        # Check if process name is running
        running = any(
            svc in (p.info.get("name") or "") or svc in " ".join(p.info.get("cmdline") or [])
            for p in psutil.process_iter(["name", "cmdline"])
        )
        # Also try systemctl for proper service status
        systemctl = _run(f"systemctl is-active {svc} 2>/dev/null")
        results.append({
            "service": svc,
            "running": running,
            "systemctl": systemctl or ("active" if running else "unknown"),
        })
    return results


def _uptime_info() -> dict:
    boot = psutil.boot_time()
    uptime_secs = (datetime.now().timestamp() - boot)
    days, rem   = divmod(int(uptime_secs), 86400)
    hours, rem  = divmod(rem, 3600)
    mins        = rem // 60
    return {
        "boot_time":    datetime.fromtimestamp(boot).strftime("%Y-%m-%d %H:%M:%S"),
        "uptime":       f"{days}d {hours}h {mins}m",
        "uptime_secs":  int(uptime_secs),
    }


@mcp.tool()
def check_server_status() -> str:
    """
    Full server health check: CPU, memory, disk, network, services, uptime.

    ⚠️ ALWAYS use when admin asks about:
    - server status / health / is the server ok
    - CPU / memory / disk / RAM usage
    - is the bot running / services running
    - server slow / high load / downtime risk
    - traffic / connections
    """
    if not is_admin():
        return json.dumps({"message": "Permission denied."})

    cpu    = _cpu_info()
    mem    = _memory_info()
    disk   = _disk_info()
    net    = _network_info()
    svcs   = _services_info()
    uptime = _uptime_info()

    # Overall health
    statuses = [cpu["status"], mem["status"]] + [p["status"] for p in disk["partitions"]]
    if "critical" in statuses:
        overall = "critical"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "healthy"

    alerts = []
    if cpu["status"] != "ok":
        alerts.append(f"CPU at {cpu['usage_percent']}% — top process: {cpu['top_processes'][0]['name'] if cpu['top_processes'] else 'unknown'}")
    if mem["status"] != "ok":
        alerts.append(f"Memory at {mem['usage_percent']}% — {mem['available_gb']} GB free")
    for p in disk["partitions"]:
        if p["status"] != "ok":
            alerts.append(f"Disk {p['mount']} at {p['usage_percent']}% — {p['free_gb']} GB free")
    for svc in svcs:
        if not svc["running"]:
            alerts.append(f"Service '{svc['service']}' is NOT running")

    return json.dumps({
        "overall_status": overall,
        "alerts":         alerts,
        "uptime":         uptime,
        "cpu":            cpu,
        "memory":         mem,
        "disk":           disk,
        "network":        net,
        "services":       svcs,
        "checked_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@mcp.tool()
def check_top_processes(sort_by: str = "cpu", limit: int = 10) -> str:
    """
    List top resource-consuming processes on the server.

    ⚠️ Use when admin asks:
    - what is using the CPU / memory
    - why is the server slow / loaded
    - which process is causing high load

    Args:
        sort_by: "cpu" (default) | "memory"
        limit:   number of processes to return (default 10)
    """
    if not is_admin():
        return json.dumps({"message": "Permission denied."})

    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    procs = sorted(
        psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username", "cmdline"]),
        key=lambda p: p.info[key] or 0,
        reverse=True,
    )[:limit]

    result = []
    for p in procs:
        cmd = " ".join(p.info["cmdline"] or [])[:80] if p.info["cmdline"] else p.info["name"]
        result.append({
            "pid":      p.info["pid"],
            "name":     p.info["name"],
            "cpu_pct":  p.info["cpu_percent"],
            "mem_pct":  round(p.info["memory_percent"] or 0, 2),
            "status":   p.info["status"],
            "user":     p.info["username"],
            "cmd":      cmd,
        })

    return json.dumps({"sort_by": sort_by, "processes": result})


# ─── DB logging helpers ────────────────────────────────────────────────────────

def _ensure_metrics_table():
    conn = get_connection()
    try:
        conn.cursor().execute("""
            CREATE TABLE IF NOT EXISTS server_metrics (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                recorded_at  DATETIME NOT NULL,
                cpu_percent  FLOAT,
                mem_percent  FLOAT,
                mem_used_gb  FLOAT,
                swap_percent FLOAT,
                disk_percent FLOAT,
                net_sent_mb  FLOAT,
                net_recv_mb  FLOAT,
                load_1m      FLOAT,
                load_5m      FLOAT,
                load_15m     FLOAT,
                connections  INT,
                INDEX idx_recorded_at (recorded_at)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def log_metrics_snapshot():
    """Called by the background scheduler to persist a metrics row."""
    _ensure_metrics_table()
    cpu  = psutil.cpu_percent(interval=1)
    vm   = psutil.virtual_memory()
    swap = psutil.swap_memory()
    net  = psutil.net_io_counters()
    load = psutil.getloadavg()
    disk = psutil.disk_usage("/")
    conns = len([c for c in psutil.net_connections(kind="inet") if c.status == "ESTABLISHED"])

    conn = get_connection()
    try:
        conn.cursor().execute("""
            INSERT INTO server_metrics
              (recorded_at, cpu_percent, mem_percent, mem_used_gb, swap_percent,
               disk_percent, net_sent_mb, net_recv_mb, load_1m, load_5m, load_15m, connections)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            datetime.now(), cpu, vm.percent, round(vm.used / 1e9, 2), swap.percent,
            disk.percent, round(net.bytes_sent / 1e6, 2), round(net.bytes_recv / 1e6, 2),
            load[0], load[1], load[2], conns,
        ))
        conn.commit()
    finally:
        conn.close()


@mcp.tool()
def get_server_metrics_history(
    date_str: str = "today",
    interval: str = "hourly",
) -> str:
    """
    Query historical server metrics (CPU, memory, disk, network) for any date.

    ⚠️ Use when admin asks:
    - server status yesterday / last week / on a specific date
    - CPU usage trend / memory trend
    - was the server overloaded on [date]
    - show me server stats for tomorrow (returns "no data yet" for future dates)

    Args:
        date_str: "today" | "yesterday" | "YYYY-MM-DD"
        interval: "hourly" (default) | "raw" (every recorded point)
    """
    if not is_admin():
        return json.dumps({"message": "Permission denied."})

    if date_str == "today":
        target = datetime.now().date()
    elif date_str == "yesterday":
        target = datetime.now().date() - timedelta(days=1)
    else:
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return json.dumps({"error": "Invalid date format. Use YYYY-MM-DD."})

    if target > datetime.now().date():
        return json.dumps({
            "date": str(target),
            "message": "No data available for future dates. Server metrics are recorded in real-time.",
        })

    _ensure_metrics_table()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)

        if interval == "hourly":
            cur.execute("""
                SELECT
                    DATE_FORMAT(recorded_at, '%%Y-%%m-%%d %%H:00') AS hour,
                    ROUND(AVG(cpu_percent), 1)  AS avg_cpu,
                    ROUND(MAX(cpu_percent), 1)  AS peak_cpu,
                    ROUND(AVG(mem_percent), 1)  AS avg_mem,
                    ROUND(MAX(mem_percent), 1)  AS peak_mem,
                    ROUND(AVG(load_1m), 2)      AS avg_load,
                    ROUND(MAX(load_1m), 2)      AS peak_load,
                    ROUND(AVG(connections), 0)  AS avg_conns,
                    COUNT(*)                    AS samples
                FROM server_metrics
                WHERE DATE(recorded_at) = %s
                GROUP BY hour
                ORDER BY hour
            """, (str(target),))
        else:
            cur.execute("""
                SELECT recorded_at, cpu_percent, mem_percent, load_1m, connections
                FROM server_metrics
                WHERE DATE(recorded_at) = %s
                ORDER BY recorded_at
            """, (str(target),))

        rows = cur.fetchall()
        if not rows:
            return json.dumps({
                "date": str(target),
                "message": "No metrics recorded for this date. Metrics logging may not have been running.",
            })

        # Daily summary
        cur.execute("""
            SELECT
                ROUND(AVG(cpu_percent), 1)  AS avg_cpu,
                ROUND(MAX(cpu_percent), 1)  AS peak_cpu,
                ROUND(AVG(mem_percent), 1)  AS avg_mem,
                ROUND(MAX(mem_percent), 1)  AS peak_mem,
                ROUND(MAX(load_1m), 2)      AS peak_load,
                COUNT(*)                    AS total_samples
            FROM server_metrics WHERE DATE(recorded_at) = %s
        """, (str(target),))
        summary = cur.fetchone()

        # Serialize datetimes
        for r in rows:
            if isinstance(r.get("recorded_at"), datetime):
                r["recorded_at"] = r["recorded_at"].strftime("%Y-%m-%d %H:%M:%S")

        alerts = []
        if summary["peak_cpu"] and summary["peak_cpu"] > 90:
            alerts.append(f"CPU peaked at {summary['peak_cpu']}%")
        if summary["peak_mem"] and summary["peak_mem"] > 90:
            alerts.append(f"Memory peaked at {summary['peak_mem']}%")
        if summary["peak_load"] and summary["peak_load"] > psutil.cpu_count():
            alerts.append(f"Load average peaked at {summary['peak_load']} (above core count)")

        return json.dumps({
            "date":     str(target),
            "interval": interval,
            "summary":  summary,
            "alerts":   alerts,
            "data":     rows,
        })
    finally:
        conn.close()
