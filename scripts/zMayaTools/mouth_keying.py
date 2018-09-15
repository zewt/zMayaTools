# This implements the keying UI for zMouthController nodes.

import glob, os, sys, time, traceback, threading
from pprint import pprint, pformat
import pymel.core as pm
import maya
from maya import OpenMaya as om
from maya.app.general import mayaMixin
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from zMayaTools import maya_helpers, maya_logging, Qt, qt_helpers
reload(qt_helpers)
from zMayaTools.menus import Menu
from maya.OpenMaya import MGlobal

log = maya_logging.get_log()

plugin_node_id = om.MTypeId(0x124749)

def set_keyframe_with_time_editor(attr, inTangentType=None, outTangentType=None):
    """
    Set a keyframe, working around problems with the time editor.
    """
    def set_to_time_editor():
        keying_target = pm.timeEditorPanel('timeEditorPanel1TimeEd', q=True, keyingTarget=True)
        if not keying_target:
            return False

        # The time editor has weird native hooks for applying keyframes, which calls
        # teSetKeyFrameOnActiveLayerOrClip in teKeyingFunctions.mel.  It's very broken:
        # it looks at the channel box to see what to key, which causes it to key the wrong
        # attributes.  We can't just set what's shown in the channel box: that requires
        # changing the selection (which will screw with the graph editor), and we can't change
        # the selection and the channel box at the same time since the CB update is async.
        #
        # Instead, bypass all of that and set the key on the time editor layer directly.
        #
        # This means we can't control tangents on time editor clips, which sucks.
        keying_target = pm.ls(keying_target)[0]
        clip_id = keying_target.node().attr('clip[0].clipid').get()
        layer_id = keying_target.attr('layerId').get()
        is_layer = isinstance(keying_target.node(), pm.nodetypes.TimeEditorClip) and keying_target.attr('layerName').get() != ''
        if not is_layer:
            return False

        # timeEditorClipLayer doesn't take tangentType arguments like pm.setKeyframe, so we have
        # to work around this the long way by temporarily changing the default.
        old_in_tangent_type = pm.keyTangent(q=True, g=True, inTangentType=True)[0]
        old_out_tangent_type = pm.keyTangent(q=True, g=True, outTangentType=True)[0]
        if inTangentType is not None:
            pm.keyTangent(g=True, inTangentType=inTangentType)
        if outTangentType is not None:
            pm.keyTangent(g=True, outTangentType=outTangentType)

        try:
            # Set the key.
            pm.timeEditorClipLayer(e=True, clipId=clip_id, layerId=layer_id, setKeyframe=True, attribute=attr)
        finally:
            # Restore the tangent type.
            pm.keyTangent(g=True, inTangentType=old_in_tangent_type)
            pm.keyTangent(g=True, outTangentType=old_out_tangent_type)

        return True

    with maya_helpers.undo():
        if set_to_time_editor():
            return

        kwargs = {}
        if inTangentType is not None:
            kwargs['inTangentType'] = inTangentType
        if outTangentType is not None:
            kwargs['outTangentType'] = outTangentType
        pm.setKeyframe(attr, **kwargs)

class KeyingWindow(MayaQWidgetDockableMixin, Qt.QDialog):
    def done(self, result):
        self.close()
        super(MayaQWidgetDockableMixin, self).done(result)

    def __init__(self):
        super(KeyingWindow, self).__init__()

        # How do we make our window handle global hotkeys?
        undo = Qt.QAction('Undo', self)
        undo.setShortcut(Qt.Qt.CTRL + Qt.Qt.Key_Z)
        undo.triggered.connect(lambda: pm.undo())
        self.addAction(undo)

        redo = Qt.QAction('Redo', self)
        redo.setShortcut(Qt.Qt.CTRL + Qt.Qt.Key_Y)
        redo.triggered.connect(lambda: pm.redo(redo=True))
        self.addAction(redo)

        self.weight_node = None
        self.shown = False
        self.callback_ids = om.MCallbackIdArray()

        self._currently_refreshing = False

        style = r'''
        /* Maya's checkbox style makes the checkbox invisible when it's deselected,
         * which makes it impossible to tell that there's even a checkbox there to
         * click.  Adjust the background color to fix this. */
        QTreeView::indicator:unchecked {
            background-color: #000;
        }
        '''
        self.setStyleSheet(style)

        self.time_change_listener = maya_helpers.TimeChangeListener(self._time_changed, pause_during_playback=False)

        # Make sure zMouthController has been generated.
        qt_helpers.compile_all_layouts()

        from zMayaTools.qt_widgets import draggable_progress_bar
        reload(draggable_progress_bar)

        from zMayaTools.qt_generated import zMouthController
        reload(zMouthController)

        self.ui = zMouthController.Ui_zMouthController()
        self.ui.setupUi(self)

        self.ui.selectionBar.setMinimum(0)
        self.ui.selectionBar.setMaximum(1000)
        self.ui.mainWeightBar.setMinimum(0)
        self.ui.mainWeightBar.setMaximum(1000)

        self.ui.selectNodeButton.clicked.connect(self.select_current_node)
        self.ui.shapeSelection1.currentIndexChanged.connect(self.shape1Changed)
        self.ui.shapeSelection2.currentIndexChanged.connect(self.shape2Changed)
        self.ui.selectedNodeDropdown.currentIndexChanged.connect(self.selectedNodeChanged)
        self.ui.setKeyShape1.clicked.connect(self.clicked_key_shape_1)
        self.ui.setKeyShape2.clicked.connect(self.clicked_key_shape_2)
        self.ui.keySelection.clicked.connect(self.clicked_key_selection)
        self.ui.keyMainWeight.clicked.connect(self.clicked_key_main_weight)
        self.ui.soloShape1.clicked.connect(self.solo_shape1)
        self.ui.soloShape2.clicked.connect(self.solo_shape2)
        self.ui.selectionBar.mouse_movement.connect(self.set_selection_bar_value)
        self.ui.mainWeightBar.mouse_movement.connect(self.set_main_weight)

        self.ui.selectionBar.set_undo_chunk_around_dragging('Dragging selection')
        self.ui.mainWeightBar.set_undo_chunk_around_dragging('Dragging weight')

        # This will call selectedNodeChanged, and trigger the rest of the refresh.
        self.refresh_weight_node_list()

    def refresh_weight_node_list(self):
        # Remember the old selection, so we can restore it if the node still exists.
        old_selected_weight_node = self.weight_node

        self.weight_nodes = pm.ls(type='zMouthController')
        self.weight_nodes.sort(key=lambda item: item.nodeName().lower())

        self.ui.selectedNodeDropdown.clear()
        self.ui.mainBox.setVisible(len(self.weight_nodes) > 0)
        self.ui.noNodes.setVisible(len(self.weight_nodes) == 0)
        if not self.weight_nodes:
            return

        for node in self.weight_nodes:
            self.ui.selectedNodeDropdown.addItem(node.nodeName())

        if old_selected_weight_node is not None and old_selected_weight_node in self.weight_nodes:
            idx = self.weight_nodes.index(old_selected_weight_node)
        else:
            idx = 0

        # This will trigger selectedNodeChanged and refresh the rest of the UI.
        self.ui.selectedNodeDropdown.setCurrentIndex(idx)

    def selectedNodeChanged(self):
        """
        The user selected a different node in the main dropdown.
        """
        index = self.ui.selectedNodeDropdown.currentIndex()

        # This happens if there are no weight nodes:
        if index == -1 or index >= len(self.weight_nodes):
            self.set_weight_node(None)
        else:
            self.set_weight_node(self.weight_nodes[index])

    def select_current_node(self):
        if self.weight_node is None:
            return

        self.weight_node.select()

    def set_weight_node(self, node):
        if node is self.weight_node:
            return

        # Unregister listeners first, since we're listening for changes on the old selected node.
        self._unregister_listeners()
        self.weight_node = node
        self._register_listeners()

        self.refresh()

    @staticmethod
    def find_controlling_attribute(attr):
        # Try to find the node that's controlling an attribute.
        #
        # The attributes are usually connected to a rig controller, and to make changes to it or place
        # keyframes we need to modify that attribute and not our own directly.  However, if the node
        # is connected to something like a character set, time editor clip, or is keyframed directly,
        # then we do need to apply changes to the attribute directly.
        #
        # There must be a way to test if an attribute is actually keyable (whether it can be modified
        # and then setKeyframed or whether that will throw an error), but I haven't been able to find it.
        
        pre_rig_node_types = [
            pm.nodetypes.AnimCurve,
            pm.nodetypes.Character,
            pm.nodetypes.TimeEditorInterpolator
        ]

        # Sanity limit for circular dependencies.  We're usually only one hop away from the controller.
        for _ in xrange(10):
            inputs = attr.listConnections(s=True, d=False, p=True)
            if not inputs:
                return attr

            # More than one input connection isn't possible.
            assert len(inputs) < 2, inputs
            input_attr = inputs[0]

            if any(isinstance(input_attr.node(), cls) for cls in pre_rig_node_types):
                return attr

            attr = input_attr

        log.warning('Limit reached for finding the controller for %s' % attr)
        return attr

    def _register_listeners(self):
        if not self.shown:
            return

        # Stop if we've already registered listeners.
        if self.callback_ids.length():
            return

        msg = om.MDGMessage()
        self.callback_ids.append(msg.addNodeAddedCallback(self._weight_nodes_changed, 'zMouthController', None))
        self.callback_ids.append(msg.addNodeRemovedCallback(self._weight_nodes_changed, 'zMouthController', None))
        self.callback_ids.append(msg.addConnectionCallback(self._connection_changed, None))
        self.callback_ids.append(om.MNodeMessage.addNameChangedCallback(om.MObject(), self._node_renamed))

        if self.weight_node is not None:
            self.callback_ids.append(om.MNodeMessage.addAttributeChangedCallback(self.weight_node.__apimobject__(), self._weight_node_changed, None))

        self.time_change_listener.register()

    def _weight_nodes_changed(self, node, data):
        # A zMouthController node was added or removed, so refresh the list.  Queue this instead of doing
        # it now, since node removed callbacks happen before the node is actually deleted.
        qt_helpers.run_async_once(self.refresh_weight_node_list)

    def _node_renamed(self, node, old_name, unused):
        # A node was renamed.  Refresh the node list if it's a zMouthController node.
        dep_node = om.MFnDependencyNode(node)
        if dep_node.typeId() != plugin_node_id:
            return
        
        qt_helpers.run_async_once(self.refresh_weight_node_list)

    def _connection_changed(self, src_plug, dst_plug, made, data):
        # When a connection is made or broken to .output, refresh the list.  Check if
        # the source node is a zMouthController node.
        src_dep_node = om.MFnDependencyNode(src_plug.node())
        if src_dep_node.typeId() != plugin_node_id:
            return

        qt_helpers.run_async_once(self.refresh_weight_node_list)
        
    def _unregister_listeners(self):
        if self.callback_ids:
            # Why is the unregistering API completely different from the registering API?
            msg = om.MMessage()
            msg.removeCallbacks(self.callback_ids)
            self.callback_ids.clear()

        self.time_change_listener.register()

    def _enable_time_listener(self):
        return pm.play(q=True, state=True) or True

    def _weight_node_changed(self, msg, plug, otherPlug, data):
        # For some reason, this is called once per output, but not actually called for changed inputs.
        # It seems to not notice when a value has changed because its input key connection has changed.
        #
        # kAttributeSet is sent for most things, like moving the time slider causing the current key
        # to change and us making changes directly.  kAttributeEval catches some things that doesn't,
        # in particular editing keys with the graph editor, but this only works if something is connected
        # to the output to trigger an evaluation.  Note that Set usually comes from the main thread, but
        # Eval tends to come from a worker thread, so we depend on the async dispatching to move this to
        # the main thread.
        if msg & (om.MNodeMessage.kAttributeSet|om.MNodeMessage.kAttributeEval):
            self._async_refresh()

    def _time_changed(self):
        # During editing and timeline scrubbing, update the UI when values change.
        self._async_refresh()

    def _async_refresh(self):
        """
        Queue a refresh.  If this is called multiple times before we do the refresh, we'll only
        refresh once.
        """
        qt_helpers.run_async_once(self.refresh)

    def refresh(self):
        """
        Update the UI to reflect the node's current values.
        """
        if not self.shown or self.weight_node is None:
            return

        # This is a little tricky.  If the selected node is deleted, _weight_nodes_changed
        # will be called and queue refresh_weight_node_list.  However, other callbacks will
        # also happen and cause refresh to be called first, so we'll try to refresh a deleted
        # node before we update to notice that it's gone.  Check for this before refreshing
        # the rest of the UI.
        if not self.weight_node.exists():
            self.refresh_weight_node_list()
            if self.weight_node is None:
                return
        
        self._currently_refreshing = True
        try:
            solo = self.weight_node.attr('solo').get()

            if solo != 0:
                selection = 0 if solo == 1 else 1
                main_weight = 1

                self.ui.selectionBar.setEnabled(False)
                self.ui.keySelection.setEnabled(False)
                self.ui.mainWeightBar.setEnabled(False)
                self.ui.keyMainWeight.setEnabled(False)
            else:
                selection = self.weight_node.attr('selection').get()
                main_weight = self.weight_node.attr('mainWeight').get()

                self.ui.selectionBar.setEnabled(True)
                self.ui.keySelection.setEnabled(True)
                self.ui.mainWeightBar.setEnabled(True)
                self.ui.keyMainWeight.setEnabled(True)

            self.ui.selectionBar.setValue(int(selection * 1000))

            self.ui.mainWeightBar.setValue(int(main_weight * 1000))

            palette = Qt.QPalette()
            color = Qt.QColor(0,255*(1-selection),0,255)
            palette.setColor(Qt.QPalette.Background, color)
            self.ui.shape1WeightColor.setAutoFillBackground(True)
            self.ui.shape1WeightColor.setPalette(palette)

            palette = Qt.QPalette()
            color = Qt.QColor(0,255*selection,0,255)
            palette.setColor(Qt.QPalette.Background, color)
            self.ui.shape2WeightColor.setAutoFillBackground(True)
            self.ui.shape2WeightColor.setPalette(palette)

            solo = self.weight_node.attr('solo').get()
            self.ui.soloShape1.setChecked(solo == 1)
            self.ui.soloShape2.setChecked(solo == 2)

            self._refresh_dropdowns()
        finally:
            self._currently_refreshing = False

    def _refresh_dropdowns(self):
        # Make a list of outputs.  The output list is sparse and the dropdown box isn't,
        # so keep track of both output indices and list indices.
        selection_names = []
        for output in self.weight_node.attr('output'):
            connected_attrs = output.listConnections(s=False, d=True, p=True)
            if not connected_attrs:
                continue
            connected_attr = connected_attrs[0]
            connected_name = pm.aliasAttr(connected_attr, q=True)
            if not connected_name:
                connected_name = connected_attr.plugAttr(longName=True)

            selection_names.append({
                'name': connected_name,
                'output_index': output.index(),
            })

        if not selection_names:
            self.ui.controls.setVisible(False)
            self.ui.noOutputs.setVisible(True)
            return
        else:
            self.ui.controls.setVisible(True)
            self.ui.noOutputs.setVisible(False)

        # The outputs are typically in an arbitrary order, so sort them.
        selection_names.sort(key=lambda item: item['name'].lower())

        self.selection_names = selection_names

        # If the current choice isn't actually connected, add an entry for it.
        choice1_shape_idx = self.weight_node.attr('choice1').get()
        choice2_shape_idx = self.weight_node.attr('choice2').get()
        choice1 = self.get_list_index_from_output_idx(choice1_shape_idx)
        choice2 = self.get_list_index_from_output_idx(choice2_shape_idx)
        if choice1 == -1:
            choice1 = len(selection_names)
            selection_names.append({
                'name': '(unknown shape #%i)' % choice1_shape_idx,
                'output_index': choice1,
            })

        if choice2 == -1 and choice1_shape_idx == choice2_shape_idx:
            # Both shapes are set to the same disconnected shape.
            choice2 = choice1
        elif choice2 == -1:
            choice2 = len(selection_names)
            selection_names.append({
                'name': '(unknown shape #%i)' % choice2_shape_idx,
                'output_index': choice2,
            })

        self.ui.shapeSelection1.clear()
        self.ui.shapeSelection2.clear()

        for item in selection_names:
            self.ui.shapeSelection1.addItem(item['name'])
            self.ui.shapeSelection2.addItem(item['name'])

        self.ui.shapeSelection1.setCurrentIndex(choice1)
        self.ui.shapeSelection2.setCurrentIndex(choice2)

    def get_list_index_from_output_idx(self, output_index):
        for idx, selection in enumerate(self.selection_names):
            if selection['output_index'] == output_index:
                return idx
        return -1


    def __del__(self):
        self.cleanup()

    def cleanup(self):
        self._unregister_listeners()

    def showEvent(self, event):
        # Why is there no isShown()?
        if self.shown:
            return
        self.shown = True

        # Refresh the node list first, to make sure self.weight_node is valid.
        self.refresh_weight_node_list()

        self._register_listeners()

        # Refresh when we're displayed.
        self._async_refresh()

        super(KeyingWindow, self).showEvent(event)

    def hideEvent(self, event):
        if not self.shown:
            return
        self.shown = False

        self._unregister_listeners()
        super(KeyingWindow, self).hideEvent(event)

    def dockCloseEventTriggered(self):
        # Bug workaround: closing the dialog by clicking X doesn't call closeEvent.
        self.cleanup()
    
    def close(self):
        self.cleanup()
        super(KeyingWindow, self).close()

    def shape1Changed(self):
        # Ignore changes made by refreshes.
        if self._currently_refreshing:
            return

        choice = self.ui.shapeSelection1.currentIndex()

        # Find the input controller.
        controlling_attr = self.find_controlling_attribute(self.weight_node.attr('choice1'))
        output_index = self.selection_names[choice]['output_index']
        controlling_attr.set(output_index)

    def shape2Changed(self):
        # Ignore changes made by refreshes.
        if self._currently_refreshing:
            return

        choice = self.ui.shapeSelection2.currentIndex()

        # Find the input controller.
        controlling_attr = self.find_controlling_attribute(self.weight_node.attr('choice2'))
        output_index = self.selection_names[choice]['output_index']
        controlling_attr.set(output_index)

    def clicked_key_shape_1(self):
        attr = self.weight_node.attr('choice1')
        controlling_attr = self.find_controlling_attribute(attr)
        set_keyframe_with_time_editor(controlling_attr, outTangentType='step')

    def clicked_key_shape_2(self):
        attr = self.weight_node.attr('choice2')
        controlling_attr = self.find_controlling_attribute(attr)
        set_keyframe_with_time_editor(controlling_attr, outTangentType='step')

    def clicked_key_selection(self):
        attr = self.weight_node.attr('selection')
        controlling_attr = self.find_controlling_attribute(attr)
        set_keyframe_with_time_editor(controlling_attr)

    def solo_shape1(self):
        self.toggle_solo(1)

    def solo_shape2(self):
        self.toggle_solo(2)

    def toggle_solo(self, idx):
        """
        If idx is 1, toggle soloing choice1.  If idx is 2, toggle soloing choice2.

        If a choice is solod, we'll display it as if it was fully weighted, to allow
        previewing shapes more easily.
        """
        attr = self.weight_node.attr('solo')
        if attr.get() == idx:
            attr.set(0)
        else:
            attr.set(idx)

        self.refresh()

    def set_selection_bar_value(self, relative, value):
        attr = self.weight_node.attr('selection')
        if relative:
            value += attr.get()
        value = min(max(value, 0), 1)

        controlling_attr = self.find_controlling_attribute(attr)
        controlling_attr.set(value)
        self._async_refresh()

    def set_main_weight(self, relative, value):
        attr = self.weight_node.attr('mainWeight')
        if relative:
            value += attr.get()
        value = min(max(value, 0), 1)

        controlling_attr = self.find_controlling_attribute(attr)
        controlling_attr.set(value)

        # If the main window isn't actually focused, it won't refresh immediately.  Force a
        # refresh, so the viewport updates responsively.
        self._async_refresh()

    def clicked_key_main_weight(self):
        attr = self.weight_node.attr('mainWeight')
        controlling_attr = self.find_controlling_attribute(attr)
        set_keyframe_with_time_editor(controlling_attr)

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()
        self.window = maya_helpers.RestorableWindow(KeyingWindow, plugins='zMouthController.py',
            uiScript='import zMayaTools.mouth_keying; zMayaTools.mouth_keying.menu.restore()')

    def restore(self):
        self.window.restore()

    def add_menu_items(self):
        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        self.add_menu_item('zMayaTools_MouthController', label='Mouth Controller', parent=menu, insertAfter='hikWindowItem',
                command=lambda unused: self.window.show(),
                standalone_path='Rigging|Mouth_Controller')

    def remove_menu_items(self):
        super(PluginMenu, self).remove_menu_items()
        
        # If the window is open when the module is unloaded, close it.
        self.window.close()

menu = PluginMenu()

