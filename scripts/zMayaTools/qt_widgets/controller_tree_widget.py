from zMayaTools import Qt
from . import widget_mixins

class ControllerTreeWidget(widget_mixins.NoDragPreviewMixin, widget_mixins.DragFromMayaMixin, Qt.QTreeWidget):
    def __init__(self, parent):
        super(ControllerTreeWidget, self).__init__(parent)

