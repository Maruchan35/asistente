import ctypes
import ctypes.wintypes as wt

monitors = []
user32 = ctypes.windll.user32

MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
    ctypes.POINTER(wt.RECT), ctypes.c_double,
)

class MONITORINFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT), ("dwFlags", wt.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]

def cb(hMon, hdcMon, lprc, dw):
    info = MONITORINFOEX()
    info.cbSize = ctypes.sizeof(MONITORINFOEX)
    user32.GetMonitorInfoW(hMon, ctypes.byref(info))
    r = info.rcMonitor
    w = r.right - r.left
    h = r.bottom - r.top
    pri = bool(info.dwFlags & 1)
    monitors.append({"w": w, "h": h, "x": r.left, "y": r.top, "pri": pri})
    return True

user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)

monitors.sort(key=lambda m: (not m["pri"], m["x"]))
for i, m in enumerate(monitors, 1):
    tag = " (Principal)" if m["pri"] else ""
    print("Monitor %d%s: %dx%d en posicion (%d,%d)" % (i, tag, m["w"], m["h"], m["x"], m["y"]))
print("Total: %d monitor(es)" % len(monitors))
