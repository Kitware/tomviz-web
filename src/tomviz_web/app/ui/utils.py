from trame.widgets import html
from trame.widgets import vuetify3 as v3
from trame_common.decorators.hot_reload import hot_reload


@hot_reload
def toolbar_btn(asset_name=None, icon: bool | str = True, click=None, **add_on):
    with v3.VBtn(
        icon=icon,
        classes="rounded mr-2",
        density="comfortable",
        variant="tonal",
        click=click,
        **add_on,
    ):
        if asset_name:
            html.Img(src=asset_name, height=30)
