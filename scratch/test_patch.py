import pyautogui
import ctypes
import unicodedata

_original_write = pyautogui.write

def _safe_write(message, *args, **kwargs):
    VK_CAPITAL = 0x14
    if ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1:
        pyautogui.press('capslock')
        
    msg = str(message).lower()
    msg = ''.join(c for c in unicodedata.normalize('NFD', msg) if unicodedata.category(c) != 'Mn')
    
    print("Writing:", msg)
    return _original_write(msg, *args, **kwargs)

pyautogui.write = _safe_write
pyautogui.typewrite = _safe_write

pyautogui.write("TÉST")
