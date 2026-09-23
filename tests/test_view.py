import asyncio

from tomviz_trame.app.data_model.view import ViewModel


class FakeWidget:
    """Counts the images a ``VtkRemoteView`` would push."""

    def __init__(self):
        self.updates = 0

    def update(self):
        self.updates += 1


def make_view():
    model = ViewModel(None)
    widget = FakeWidget()
    model.widget_view = widget  # not a VtkRemoteView: logs a type warning
    return model, widget


def test_renders_in_one_loop_iteration_are_merged():
    """Every sink coloring through an edited map asks for a render; the
    view pushes one image for all of them, then accepts new requests."""

    async def run():
        model, widget = make_view()
        model.render()
        model.render()
        assert widget.updates == 0
        await asyncio.sleep(0)
        assert widget.updates == 1

        model.render()
        await asyncio.sleep(0)
        assert widget.updates == 2

    asyncio.run(run())


def test_render_without_a_loop_is_immediate():
    model, widget = make_view()
    model.render()
    assert widget.updates == 1
