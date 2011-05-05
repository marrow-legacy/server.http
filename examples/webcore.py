import web.core

from marrow.server.http import HTTPServer
from marrow.server.http.adapt import wsgi1


class RootController(web.core.Controller):
    def index(self):
        return 'Hello world!'
    
    def hello(self, name):
        return "Hello, %(name)s!" % dict(name=name)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    app = web.core.Application.factory(root=RootController, debug=False, **{'web.static': False})
    
    HTTPServer(None, 8080, threaded=5, fork=2, application=wsgi1(app)).start()
