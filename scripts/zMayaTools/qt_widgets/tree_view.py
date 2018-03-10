from zMayaTools import Qt

class TreeView(Qt.QTreeView):
    def __init__(self, parent):
        super(TreeView, self).__init__(parent)

        self.is_during_mouse_release = False
        self.performing_edit_event_index = None
        self.performing_edit_event_item = None

    def edit(self, index, trigger, event):
        try:
            self.performing_edit_event_index = index
            if index.model() is not None:
                source_index = index.model().mapToSource(index)
                source_item = source_index.model().itemFromIndex(source_index)
                self.performing_edit_event_item = source_item
            
            return super(TreeView, self).edit(index, trigger, event)
        finally:
            self.performing_edit_event_index = None
            self.performing_edit_event_item = None

    def mouseReleaseEvent(self, event):
        self.is_during_mouse_release = True
        try:
            return super(TreeView, self).mouseReleaseEvent(event)
        finally:
            self.is_during_mouse_release = False

    def checkbox_toggled(self, item, value):
        """
        This is called by items when their checked state is changed by a call to setData.
        If we're in the middle of an edit on that item, assume that the edit caused the
        toggle and apply the same change to all selected items in the same column.
        """
        if value == Qt.Qt.PartiallyChecked:
            return
        
        if self.performing_edit_event_item is not item:
            return

        selected_indexes = item.view.selectedIndexes()
        selected_indexes = [idx.model().mapToSource(idx) for idx in selected_indexes]
        selected_items = [idx.model().itemFromIndex(idx) for idx in selected_indexes]

        # Only do this if a selected item is being changed.
        if not any(item is selected_item for selected_item in selected_items):
            return

        for other_item in selected_items:
            if other_item is item:
                continue

            # Only change items in the same column as us.
            if other_item.index().column() != item.index().column():
                continue

            if other_item.isCheckable():
                other_item.setData(value, Qt.Qt.CheckStateRole)

    def selectionCommand(self, index, event):
        if self.is_during_mouse_release:
            # Work around QT.  If a click on an item doesn't cause it to be selected
            # (QAbstractItemView::mousePressEvent), QAbstractItemView::mouseReleaseEvent will 
            # try to select the item instead.  We don't want that.  If you click on a checkbox,
            # the edit will eat the click so it won't cause a selection, so if we let this
            # happen, clicking a checkbox when multiple items are selected will select just the
            # clicked item after toggling the checkboxes.
            return Qt.QItemSelectionModel.NoUpdate

#        if event.type() == Qt.QEvent.MouseButtonPress:
#            button = event.button()
#            modifiers = event.modifiers()
#            is_right_button = bool(button & Qt.Qt.RightButton)
#            shift = bool(modifiers & Qt.Qt.ShiftModifier)
#            control = bool(modifiers & Qt.Qt.ControlModifier)
#            selected = self.selectionModel().isSelected(index)
#            return Qt.QItemSelectionModel.ClearAndSelect
#        if event.type() == Qt.QEvent.MouseButtonRelease:
#            return Qt.QItemSelectionModel.NoUpdate
        return super(TreeView, self).selectionCommand(index, event)

