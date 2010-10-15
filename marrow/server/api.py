# encoding: utf-8

"""Server protocol API."""



__all__ = ['IProtocol']


class IProtocol(object):
    def __init__(self, server):
        pass
    
    def start(self, server):
        pass
    
    def stop(self, server):
        pass
    
    def connected(self, server, client, address):
        """Return True if the connection should not be recorded.
        
        The Server will deal with closing the connection for us.
        """
        
        log.debug("Connection from %r -- %r.", client, address)
    
    def readable(self, server, client):
        """Override this and submit jobs by calling server.worker(job).
        
        Executed in the main thread.
        """
        raise NotImplementedError
    
    def writeable(self, server, client):
        """Write responses out to the client.
        
        Retrieve the response from server.responses[client].
        
        Executed in the responder thread.
        """
        raise NotImplementedError
    
    def process(self, server, client, request):
        """Process a request, usually generating a response.
        
        Request is read out for us, responses should be appended to server.resopnses[client].
        
        Executed in a worker thread.
        """
        raise NotImplementedError
