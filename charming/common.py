import functools
from . import constants
from .app import renderer
from .app import context
from .utils import logger


def capture_exception(foo):
    @functools.wraps(foo)
    def wrapped(*args, **kw):
        try:
            return foo(*args, **kw)
        except Exception as e:
            logger.debug(e)
            context.close()
            raise e

    return wrapped


def add_on_return(foo):
    @functools.wraps(foo)
    def wrapped(*args, **kw):
        element = foo(*args, **kw)
        renderer.add_element(element)
    return wrapped


def get_bounding_rect_by_mode(a, b, c, d, mode):
    if mode == constants.RADIUS:
        x1 = a - c
        y1 = b - d
        x2 = a + c
        y2 = b - d
        x3 = a + c
        y3 = b + d
        x4 = a - c
        y4 = b + d
    elif mode == constants.CORNERS:
        x1 = a
        y1 = b
        x2 = c
        y2 = b
        x3 = c
        y3 = d
        x4 = a
        y4 = d
    elif mode == constants.CENTER:
        x1 = a - c / 2
        y1 = b - d / 2
        x2 = a + c / 2
        y2 = b - d / 2
        x3 = a + c / 2
        y3 = b + d / 2
        x4 = a - c / 2
        y4 = b + d / 2
    else:
        x1 = a
        y1 = b
        x2 = a + c
        y2 = b
        x3 = a + c
        y3 = b + d
        x4 = a
        y4 = b + d
    return (x1, y1, x2, y2, x3, y3, x4, y4)
