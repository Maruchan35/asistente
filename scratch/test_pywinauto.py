
from pywinauto import Desktop
import pygetwindow as gw

active = gw.getActiveWindow()
if active:
    print(f'Active window: {active.title}')
    try:
        app = Desktop(backend='uia').window(handle=active._hWnd)
        # Find all elements
        descendants = app.descendants()
        for d in descendants[:10]:
            print(d.window_text(), d.rectangle())
    except Exception as e:
        print(e)

