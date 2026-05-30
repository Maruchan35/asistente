
import mss
with mss.mss() as sct:
    print('Monitors:', sct.monitors)
    mon = sct.monitors[0]
    print('All in one:', mon)

