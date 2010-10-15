# encoding: utf-8

"""On-demand thread pool.

Worker threads are spawned based on demand at the time a message is added to the queue.
"""

import logging

from copy import deepcopy
from math import ceil

from Queue import Queue, Empty
from threading import Event, Thread


__all__ = ['ThreadPool']

log = logging.getLogger(__name__)



class ThreadPool(object):
    def __repr__(self):
        return "ThreadPool(%d jobs, %d of %d threads)" % (self.queue.qsize(), self.pool, self.maximum)
    
    def __init__(self, protocol, minimum=5, maximum=100, divisor=10, timeout=60):
        log.debug("Thread pool starting.")
        log.debug("%d threads minimum, %d maximum, %d jobs per thread, %d second timeout.", minimum, maximum, divisor, timeout)
        
        self.pool = 0
        self.queue = Queue()
        self.finished = Event()
        
        self.protocol = protocol
        
        self.minimum = minimum
        self.maximum = maximum
        self.divisor = divisor
        self.timeout = timeout
        
        log.debug("Spawning initial threads.")
        
        for i in range(minimum):
            self.spawn()
        
        log.debug("Thread pool ready.")
    
    def __call__(self, request):
        self.queue.put(deepcopy(request))
        optimum = self.optimum
        
        if self.pool < optimum:
            spawn = optimum - self.pool
            log.debug("Spawning %d thread%s...", spawn, '' if spawn == 1 else 's')
            
            for i in range(spawn):
                self.spawn()
            
            return True
        
        return False
    
    @property
    def optimum(self):
        return max(self.minimum, min(self.maximum, ceil(self.queue.qsize() / float(self.divisor))))
    
    def stop(self):
        log.debug("Thread pool shutting down.")
        self.finished.set()
        
        log.debug("Waiting for workers to finish.")
        self.queue.join()
        
        log.debug("Stopping threads waiting for work.")
        for i in range(self.pool):
            self.queue.put(None)
        
        self.queue.join()
    
    def spawn(self):
        log.debug("Spawning thread.")
        thread = Thread(target=self.worker)
        thread.start()
        self.pool += 1
    
    def worker(self):
        log.debug("Worker thread starting up.")
        
        try:
            jobs = 0
            
            while True:
                try:
                    request = self.queue.get(True, self.timeout)
                    
                    if request is None and self.finished.isSet():
                        log.debug("Worker death by external request.")
                        self.queue.task_done()
                        break
                    
                    self.protocol.request(request)
                    jobs += 1
                    self.queue.task_done()
                
                except Empty:
                    if self.finished.isSet():
                        log.debug("Worker death by external request.")
                        break
                    
                    if self.pool <= self.minimum:
                        log.debug("Refusing to die from starvation to preserve minimum thread count.")
                        continue
                    
                    log.debug("Worker death from starvation.")
                    break
                
                if jobs == self.divisor:
                    log.debug("Worker death form exhaustion.")
                    
                    if self.pool <= self.minimum:
                        self.spawn()
                    
                    break
        
        except:
            log.exception("Internal error in worker thread.")
        
        self.pool -= 1
        log.debug("Worker thread finished.")



if __name__ == '__main__':
    """This takes about 50 seconds to run on my computer."""
    
    import logging
    
    logging.basicConfig(level=logging.DEBUG)
    
    class Protocol(object):
        def request(self, request):
            log.info("Processing: %r", request)
    
    pool = ThreadPool(Protocol(), minimum=1)
    
    for i in range(10000):
        log.warn("Adding request.  Pool size: %d", pool.queue.qsize())
        pool(i)
    
    pool.stop()