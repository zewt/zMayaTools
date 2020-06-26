from . import widget_mixins
from zMayaTools import Qt

class ListWidgetWithDrop(widget_mixins.NoDragPreviewMixin, widget_mixins.DragFromMayaMixin, Qt.QListWidget):
    def __init__(self, parent):
        super(ListWidgetWithDrop, self).__init__(parent)

