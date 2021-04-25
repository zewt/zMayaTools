import glob, os, sys, time
import pymel.core as pm
import maya
from maya import OpenMaya as om
from zMayaTools import maya_helpers, maya_logging, Qt, qt_helpers, maya_callbacks, dockable_window
from zMayaTools.menus import Menu

import maya.OpenMayaUI as omui
from maya.OpenMaya import MGlobal

try:
    from importlib import reload
except ImportError:
    pass

log = maya_logging.get_log()

class CreateCurve(object):
    @classmethod
    def create(cls):
        maya_helpers.load_plugin('zCreateCurve')
        node = pm.createNode('zCreateCurve', skipSelect=True)
        return cls(node)

    def __init__(self, node):
        assert node is not None
        self.node = node

    @property
    def curve_indices(self):
        """
        Return all existing curve indices.

        Curves exist if their outputCurve has an output connection.
        """
        result = []
        for output in self.node.outputCurve:
            if pm.listConnections(output, s=False, d=True):
                result.append(output.index())
        return result

    def curve_output(self):
        attr = self.node.outputCurve
        conns = pm.listConnections(attr, s=False, d=True, p=True)
        if conns:
            return conns[0]
        else:
            return None

    def curve_output_attr(self):
        return self.node.outputCurve

    def add_curve_output(self):
        """
        Create a nurbsCurve and attach it to the output.
        """
        # There's no skipSelect parameter to curve().  Save the selection and restore it manually.
        old_selection = pm.ls(sl=True)

        # Create a curve shape for the output.  Note that we need to use curve() and not just create
        # a nurbsCurve.  If a nurbsCurve is created directly it won't have any data, MFnNurbsCurve
        # will fail with kInvalidParameter, and PyNode will spam "Could not create desired MFn. Defaulting
        # to MFnDagNode" warnings.
        curve_node = pm.curve(p=[(0, 0, 0)]).getShape()

        # Disable inheritsTransform and lock the transform, so the curve always stays aligned to the transforms.
        transform_node = curve_node.getTransform()
        transform_node.inheritsTransform.set(False)
        transform_node.translate.set(lock=True)
        transform_node.rotate.set(lock=True)
        transform_node.scale.set(lock=True)

        pm.select(old_selection, ne=True)

        # Add the curve to the node.
        self.node.outputCurve.connect(curve_node.create)

        return curve_node
 
    def get_transforms(self):
        curve = self.node
        result = []
        for transform_attr in curve.input:
            conn = pm.listConnections(transform_attr, p=True, s=True, d=False)
            if not conn:
                continue
            result.append(conn[0])
        return result

    def set_transforms(self, transforms):
        curve = self.node

        # Disconnect all transforms.
        for attr in curve.input:
            conn = pm.listConnections(attr, p=True, s=True, d=False)
            if not conn:
                continue
            conn[0].disconnect(attr)

        # Assign the new ones.
        for idx, transform in enumerate(transforms):
            transform.connect(curve.input[idx])

# A thin wrapper to work around PySide2 breaking when passing a PyNode as a QVariant:
#
# TypeError: object of type 'node' has no len()
class DataWrapper(object):
    def __init__(self, data):
        self.data = data

class CreateCurveEditor(dockable_window.DockableWindow):
    def __init__(self):
        super(CreateCurveEditor, self).__init__()

        self.currently_refreshing = False

        self.node_listener = maya_callbacks.NodeChangeListener('zCreateCurve', self.refresh_all)
        self.callbacks = maya_callbacks.MayaCallbackList()
        self.callbacks.add(self.refresh_on_selection_changed, lambda func: om.MEventMessage.addEventCallback('SelectionChanged', func))

        for delete_key in (Qt.Qt.Key_Backspace, Qt.Qt.Key_Delete):
            shortcut = Qt.QShortcut(Qt.QKeySequence(delete_key), self, None, None, Qt.Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self.remove_selected_transforms_from_curve)

        from zMayaTools.qt_generated import zCreateCurve
        reload(zCreateCurve)

        # Set up the UI.
        self.ui = zCreateCurve.Ui_zCreateCurve()
        self.ui.setupUi(self)

        # Set up the menu bar.
        self.menubar = Qt.QMenuBar()
        self.layout().setMenuBar(self.menubar)
        menubar = self.menubar

        # If we create menus with addMenu and addAction, the parent is set, but the object is
        # still deleted, and we get "internal C++ object already deleted" errors later.  This seems
        # like a QT or PySide bug.

        def add_menu(text):
            menu = Qt.QMenu(text, self.menubar)
            self.menubar.addAction(menu.menuAction())
            return menu

        def add_menu_item(menu, text, func):
            action = Qt.QAction(text, menu)
            menu.addAction(action)
            action.triggered.connect(func)
            return action

        menu = add_menu('Node')
        self.menu_create_node = add_menu_item(menu, 'Create Node', self.create_and_select_node)
        self.menu_delete_node = add_menu_item(menu, 'Delete Node', self.delete_node)
        self.menu_select_node = add_menu_item(menu, 'Select Node', self.select_current_node)
        self.menu_select_curve = add_menu_item(menu, 'Select Output Curve', self.select_current_curve)

        self.ui.selectNodeButton.clicked.connect(self.select_current_node)
        self.ui.createNodeButton.clicked.connect(self.create_and_select_node)
        self.ui.addToCurveButton.clicked.connect(self.append_selected_transforms_to_curve)
        self.ui.removeFromCurveButton.clicked.connect(self.remove_selected_transforms_from_curve)

        self.ui.nodeDropdown.currentTextChanged.connect(self.current_node_changed)

        self.ui.transformList.setSelectionMode(Qt.QAbstractItemView.ExtendedSelection)
        self.ui.transformList.viewport().setAcceptDrops(True)
        self.ui.transformList.setDropIndicatorShown(True)

        self.ui.transformList.setDragDropMode(Qt.QAbstractItemView.DragDrop)
        self.ui.transformList.checkDragFromMaya = lambda nodes: nodes # allow dropping anything

        self.ui.transformList.dragged_internally.connect(self.dragged_internally)
        self.ui.transformList.dragged_from_maya.connect(self.dragged_from_maya)

        self.ui.transformList.itemSelectionChanged.connect(self.transform_selection_changed)
        self.ui.transformList.itemDoubleClicked.connect(self.double_clicked_transform)

    def shownChanged(self):
        super(CreateCurveEditor, self).shownChanged()

        self.callbacks.registered = self.shown
        self.node_listener.registered = self.shown

        # Refresh when we're displayed.
        if self.shown:
            self.refresh_all()

    def refresh_on_selection_changed(self):
        # Enable the "add transforms" button if anything is selected.  We'll get called
        # for all selections, so we don't check whether the selection is valid here, just
        # whether there is one.
        anything_selected = len(pm.ls(sl=True))
        self.ui.addToCurveButton.setEnabled(anything_selected)

    def current_node_changed(self, name):
        """
        Refresh the UI when the selected node changes.
        """
        if self.currently_refreshing:
            return

        self.refresh_all()

    @property
    def current_node(self):
        # Return the selected node.
        node_dropdown_data = self.ui.nodeDropdown.currentData()
        if node_dropdown_data is None:
            return None
        return node_dropdown_data.data

    @current_node.setter
    def current_node(self, node):
        """
        Select the given zCreateCurve node in the node dropdown.
        """
        # We can't use nodeDropdown.findData for this, since it doesn't do Python equality.
        for idx in range(self.ui.nodeDropdown.count()):
            data = self.ui.nodeDropdown.itemData(idx)
            if data.data == node:
                self.ui.nodeDropdown.setCurrentIndex(idx)

    def select_transform_rows(self, rows):
        """
        Select the given rows in the transform list.
        """
        selection_model = self.ui.transformList.selectionModel()
        selection_model.reset()

        if not rows:
            return

        # Set the keyboard selection to the last item.  Note that setCurrentIndex also resets the
        # selection, so do this first.
        model_index = self.ui.transformList.model().createIndex(rows[-1], 0)
        self.ui.transformList.setCurrentIndex(model_index)

        for row in rows:
            model_index = self.ui.transformList.model().createIndex(row, 0)
            selection_model.select(model_index, Qt.QItemSelectionModel.Select)

    def select_current_node(self):
        """
        Set the Maya selection to the current node.
        """
        if not self.current_node:
            return
        pm.select(self.current_node, ne=True)

    def select_current_curve(self):
        """
        Set the Maya selection to the output curve.
        """
        if not self.current_node:
            return

        curve = CreateCurve(self.current_node)
        curve_output = curve.curve_output()
        if curve_output is None:
            return
        
        curve_output = curve_output.node()

        # For shapes, select the transform instead.
        if isinstance(curve_output, pm.nodetypes.Shape):
            curve_output = curve_output.getTransform()

        pm.select(curve_output, ne=True)

    def create_and_select_node(self, add_selected_transforms=True):
        """
        Create a new zCreateCurve node and an output curve.  Select the curve.
        
        If transforms are selected in the scene, add them to the new curve if add_selected_transforms is true.
        """
        with maya_helpers.undo():
            nodes = pm.ls(sl=True)
            attrs = self.get_matrix_from_nodes(nodes)

            # Create the curve.
            curve = CreateCurve.create()
            self.refresh_all()
            self.current_node = curve.node

            # Create a curve node.
            output_curve = curve.add_curve_output()
            
            if add_selected_transforms:
                # Add selected transforms to it.
                curve = CreateCurve(self.current_node)
                curve.set_transforms(attrs)

            # Refresh and select the new curve.
            self.refresh_all()

            pm.select(output_curve.getTransform())

    def delete_node(self):
        if not self.current_node:
            return

        pm.delete(self.current_node)
        self.refresh_all()

    def add_transforms_to_curve(self, nodes, pos=0):
        """
        Insert nodes into the transform list at the given position.

        If pos is None, add at the end.
        """
        with maya_helpers.undo():
            curve = CreateCurve(self.current_node)
            attrs = self.get_matrix_from_nodes(nodes)

            # Add the attributes to the transform list.  We don't prevent adding duplicates.
            transforms = curve.get_transforms()
            if pos is None:
                pos = len(transforms)
            transforms[pos:pos] = attrs
            curve.set_transforms(transforms)

            # Refresh now, so we can select the new items.
            self.refresh_all()

            # Select the items that we added.
            self.select_transform_rows(range(pos, pos+len(nodes)))

    def append_selected_transforms_to_curve(self):
        nodes = pm.ls(sl=True)
        attrs = self.get_matrix_from_nodes(nodes)

        if not attrs:
            log.info('Select one or more transforms to add to the curve')
            return

        # If we have no node, create one.
        if not self.current_node:
            self.create_and_select_node()
        else:
            self.add_transforms_to_curve(attrs, pos=None)

    @classmethod
    def get_matrix_from_nodes(cls, nodes):
        # The selection can contain nodes or attributes.  For nodes, figure out which matrix attribute
        # to use.  Maya doesn't have any consistency between attributes, so if we want this to work with
        # different node types, we need to handle them explicitly.
        result = []
        for node in nodes:
            if isinstance(node, pm.nodetypes.Transform):
                result.append(node.worldMatrix[0])
            elif isinstance(node, pm.general.Attribute) and node.type() == 'matrix':
                if node.isArray():
                    node = node[0]
                result.append(node)
        return result

    def get_drag_target_idx(self, target, indicator_position):
        """
        Given a target row in transformList and an indicator position, return the index
        in the current curve where the user dragged.
        """
        # Figure out where the drop should be inserted.
        if target is not None:
            pos = self.ui.transformList.indexFromItem(target).row()
        else:
            pos = 0

        if indicator_position == Qt.QAbstractItemView.DropIndicatorPosition.OnViewport:
            return self.ui.transformList.count()
        elif indicator_position in (Qt.QAbstractItemView.DropIndicatorPosition.OnItem, Qt.QAbstractItemView.DropIndicatorPosition.BelowItem):
            return pos + 1
        else: # Qt.QAbstractItemView.DropIndicatorPosition.AboveItem
            return pos

    def dragged_from_maya(self, nodes, target, indicator_position):
        # If we have no node, create one.  Don't add the selection while creating the node.
        if not self.current_node:
            self.create_and_select_node(add_selected_transforms=False)

        pos = self.get_drag_target_idx(target, indicator_position)
        self.add_transforms_to_curve(nodes, pos=pos)

    def remove_selected_transforms_from_curve(self):
        if not self.current_node:
            return

        with maya_helpers.undo():
            selected_rows = set(idx.row() for idx in self.ui.transformList.selectedIndexes())
            if not selected_rows:
                return

            # Remember the first selection, so we can reselect it below.
            first_selected_dropdown_idx = min(selected_rows)

            curve = CreateCurve(self.current_node)
            transforms = curve.get_transforms()
            new_transforms = []
            for idx, transform in enumerate(transforms):
                if idx not in selected_rows:
                    new_transforms.append(transform)

            curve.set_transforms(new_transforms)

            # Refresh the list, and select the first index that was selected.  This way, if you delete
            # the first entry, we leave the new first entry selected instead of deselecting.
            self.refresh_all()
            self.select_transform_rows([first_selected_dropdown_idx])

    def dragged_internally(self, target, event, indicator_position):
        # We shouldn't get an internal drag with no selection (there's nothing to drag).
        if not self.current_node:
            return

        with maya_helpers.undo():
            # The position we're moving the selection to:
            pos = self.get_drag_target_idx(target, indicator_position)

            curve = CreateCurve(self.current_node)
            orig_transforms = curve.get_transforms()

            # The selected rows, and associated transforms:
            selected_rows = [idx.row() for idx in self.ui.transformList.selectedIndexes()]
            selected_transforms = [orig_transforms[row] for row in selected_rows]

            new_transforms = []
            output_idx = None
            for idx, transform in enumerate(orig_transforms):
                # If this is the position we're moving the selection to, add them.
                if idx == pos:
                    output_idx = len(new_transforms)
                    new_transforms.extend(selected_transforms)

                # If this transform isn't one of the ones we're moving, add it.
                if idx not in selected_rows:
                    new_transforms.append(transform)

            # If pos is at the end, we didn't add selected_transforms above, so do it now.
            if pos == len(orig_transforms):
                output_idx = len(new_transforms)
                new_transforms.extend(selected_transforms)

            curve.set_transforms(new_transforms)

            # Update the list so we can update the selection.
            self.populate_transform_list()

            # Reselect the items that we added.
            self.select_transform_rows(range(output_idx, output_idx+len(selected_transforms)))

    def refresh_after_transform_selection_changed(self):
        # When at least one transform is selected, enable the "remove from curve" button.
        any_transforms_selected = len(self.ui.transformList.selectedIndexes()) > 0
        self.ui.removeFromCurveButton.setEnabled(any_transforms_selected)

    def transform_selection_changed(self):
        # When the transform list selection changes, refresh the "remove from curve" button.
        self.refresh_after_transform_selection_changed()

    def double_clicked_transform(self, item):
        # Select transforms on double-click.
        node = item.transform_attr.node()
        if isinstance(node, pm.nodetypes.Shape):
            node = node.getTransform()

        pm.select(node, ne=True)

    def refresh_all(self):
        self.populate_node_list()
        self.populate_transform_list()
        self.refresh_on_selection_changed()

        self.ui.selectNodeButton.setEnabled(self.current_node is not None)
        self.menu_delete_node.setEnabled(self.current_node is not None)
        self.menu_select_node.setEnabled(self.current_node is not None)

        self.refresh_after_transform_selection_changed()

        # Enable or disable buttons that require a curve.
        curve_available = False
        if self.current_node:
            curve = CreateCurve(self.current_node)
            curve_available = curve.curve_output() is not None
        self.menu_select_curve.setEnabled(curve_available)

    def populate_node_list(self):
        self.currently_refreshing = True

        # Remember which node was selected.
        old_selection_index = self.ui.nodeDropdown.currentIndex()
        old_selection_node = self.current_node

        # If the old selection no longer exists, we'll select a nearby index.
        if not old_selection_node:
            old_selection_node = None

        self.ui.nodeDropdown.clear()

        # Add all zCreateCurve nodes to the list.
        nodes = pm.ls(type='zCreateCurve')
        for node in nodes:
            self.ui.nodeDropdown.addItem(node.nodeName(), DataWrapper(node))
 
        # If the selected node is still in the list, reselect it.
        if old_selection_node is not None:
            self.current_node = old_selection_node
        else:
            # We have no selection, or the old selection no longer exists.  Select the
            # index we were on (keeping it in bounds), so we select a nearby entry in
            # the list.
            old_selection_index = max(old_selection_index, 0)
            old_selection_index = min(old_selection_index, self.ui.nodeDropdown.count()-1)
            self.ui.nodeDropdown.setCurrentIndex(old_selection_index)

        self.currently_refreshing = False

    def populate_transform_list(self):
        self.currently_refreshing = True
        try:
            # Remember which indexes were selected.
            old_selection = [idx.row() for idx in self.ui.transformList.selectedIndexes()]

            if self.current_node is None:
                new_transform_list = []
            else:
                curve = CreateCurve(self.current_node)
                new_transform_list = curve.get_transforms()

            self.ui.transformList.clear()
            self.current_transform_list = new_transform_list

            for transform_attr in new_transform_list:
                # The input connection usually goes to worldMatrix[0].  Only show the attribute if
                # it's connected to something else.
                name = transform_attr.name()
                if transform_attr.attrName(longName=True) == 'worldMatrix':
                    # Work around a PyMEL consistency: node.nodeName() returns just the node name,
                    # but attr.nodeName() returns the disambiguated name.  We just want the node
                    # name.
                    name = transform_attr.node().nodeName()
                else:
                    name = '%s.%s' % (transform_attr.node().nodeName(), transform_attr.attrName(longName=True))

                item = Qt.QListWidgetItem(name)
                item.transform_attr = transform_attr
                self.ui.transformList.addItem(item)

            # Reselect the old selection.  These might not point at the same things, but it prevents
            # losing the selection whenever we refresh.
            self.select_transform_rows(old_selection)

            # Make sure the "remove from curve" button state is enabled after we change the list.
            self.refresh_after_transform_selection_changed()
            
        finally:
            self.currently_refreshing = False

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()

        self.window = maya_helpers.RestorableWindow(CreateCurveEditor, plugins='zCreateCurve',
            module='zMayaTools.zCreateCurve', obj='menu.window')

    def _add_menu_items(self):
        menu = 'MayaWindow|mainCreateMenu'

        # Make sure the menu is built.
        pm.mel.eval('ModCreateMenu "%s";' % menu)

        # Add to the end of the "Curve Tools" section of Create.
        self.add_menu_item('zMayaTools_zCreateCurve', label='Create Curve', parent='%s|createCurveTools' % menu,
                command=lambda unused: self.window.show(),
                image=pm.runTimeCommand('CVCurveTool', q=True, i=True),
                top_level_path='Rigging|CreateCurve')

    def _remove_menu_items(self):
        super(PluginMenu, self)._remove_menu_items()

        # If the window is open when the module is unloaded, close it.
        self.window.close()

menu = PluginMenu()

        
