import pprint
import web.core

from marrow.server.http import HTTPServer
from marrow.server.http.adapt import wsgi1


class RootController(web.core.Controller):
    def __default__(self, *args, **kw):
        return "Hello world!"
        #web.core.response.content_type = "text/plain"
        #return pprint.pformat(web.core.request.environ)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.WARN)
    
    app = web.core.Application.factory(root=RootController, debug=True, **{'web.static': False})
    
    HTTPServer(None, 8080, fork=1, application=wsgi1(app)).start()
