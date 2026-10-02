# dev.py  -  run with:  python dev.py
import subprocess, sys, time, os

FILE = "resort_v2.py"          # change to your filename

def mtime():
    return os.path.getmtime(FILE)

while True:
    proc = subprocess.Popen([sys.executable, FILE])
    last = mtime()
    while proc.poll() is None:
        time.sleep(0.4)
        if mtime() != last:            # file saved -> restart
            proc.terminate()
            proc.wait()
            break
    else:
        break                          # you closed the window yourself -> stop
    time.sleep(0.2)