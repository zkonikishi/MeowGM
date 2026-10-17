"""Built-in synthetic worker. It never opens a socket, file, game, or database."""
import json
import sys
import threading
import time

def main():
    lock=threading.Lock();done=threading.Event()
    def emit(kind):
        with lock:
            print(json.dumps({'protocol':'meowgm-fixture-v1','type':kind}),flush=True)
    emit('ready')
    def heartbeat():
        while not done.wait(.5):emit('heartbeat')
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        for line in sys.stdin:
            if line.strip()=='stop':
                emit('stopped');break
    finally:done.set();thread.join(timeout=1)

if __name__=='__main__':main()
