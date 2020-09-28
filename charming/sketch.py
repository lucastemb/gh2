import time
from .renderer import Renderer


hooks_map = {}
frame_rate = 30
is_loop = True
renderer = Renderer()
frame_count = 0


def add_hook(name, hook):
    hooks_map[name] = hook


def run():
    try:
        global frame_count
        setup_hook = hooks_map['setup']
        draw_hook = hooks_map['draw']

        if not setup_hook or not draw_hook:
            return

        setup_hook()
        renderer.setup()
        while True:
            if is_loop:
                draw_hook()
                renderer.draw()
            renderer.listen()
            frame_count += 1
            time.sleep(1 / frame_rate)
    except Exception as e:
        print(e)
    finally:
        # pass
        renderer.close()
