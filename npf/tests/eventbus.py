import multiprocessing
import os

class EventBus:
    def __init__(self, m = None):
        if not m:
            m = multiprocessing.Manager()
        self.c = m.Condition()
        self.list = m.list()
        self.terminated = m.Event()

    def post(self, ev):
        self.c.acquire()
        self.list.append(ev)
        self.c.notify_all()
        self.c.release()

    def terminate(self):
        self.c.acquire()
        self.terminated.set()
        self.c.notify_all()
        self.c.release()

    def wait_for_termination(self, t):
        self.c.acquire()
        c = t
        step = 0.1
        while c > 0 and not self.is_terminated():
            self.c.wait(step)
            c = c - step

        self.c.release()

    def is_terminated(self):
        self.c.acquire()
        r = self.terminated.is_set()
        self.c.release()
        return r

    def listen(self, ev):
        self.c.acquire()
        i = 0
        while len(self.list) == 0:
            self.c.wait()
            if self.terminated.is_set():
                self.c.release()
                return
        while self.list[i] != ev:
            i += 1
            if i == len(self.list):
                self.c.wait()
                if self.terminated.is_set():
                    self.c.release()
                    return
        self.c.release()



