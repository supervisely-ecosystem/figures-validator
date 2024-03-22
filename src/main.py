import supervisely as sly
from supervisely.app.widgets import Container

import src.globals as g
import src.ui.input as input
import src.ui.output as output
import src.ui.settings as settings

layout = Container(widgets=[input.card, settings.card, output.card])

# * If the app uses static dir, it should be passed as a parameter.
# * If not needed the app can be initialized without static_dir parameter.
# * app = sly.Application(layout=layout)
app = sly.Application(layout=layout, static_dir=g.STATIC_DIR)
