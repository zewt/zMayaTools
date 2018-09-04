from pymel import core as pm
import maya.OpenMaya as om
import maya.OpenMayaAnim as oma
import maya.OpenMayaUI as omui
from maya.app.general import mayaMixin
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from zMayaTools import qt_helpers, maya_logging, maya_helpers, Qt
from zMayaTools.menus import Menu
import bisect, os, sys, time
from collections import defaultdict
from pprint import pprint, pformat

# Run this to reload the UI for development (this won't reload the plugin):
# def go():
#     from zMayaTools import keyframe_naming
#     keyframe_naming.menu.remove_menu_items()
#     keyframe_naming.menu.hide()
#     reload(keyframe_naming)
#     keyframe_naming.menu.add_menu_items()
#     keyframe_naming.menu.show()
# go()

log = maya_logging.get_log()

plugin_node_id = om.MTypeId(0x12474B)

def get_singleton(create=True):
    """
    Return the singleton node.  If create is true, create it if it doesn't exist,
    otherwise return None.
    """
    nodes = pm.ls(':zKeyframeNaming', type='zKeyframeNaming')
    if not nodes:
        if not create:
            return None
        return pm.createNode('zKeyframeNaming', name=':zKeyframeNaming')
    assert len(nodes) == 1
    return nodes[0]

def _get_key_index_at_frame(frame):
    """
    Get the key index for the current frame.

    If there's no key at the current frame, return None rather than the value of
    the most recent frame.
    """
    keys = get_singleton(create=False)
    if keys is None:
        return None

    idx = pm.keyframe(keys.attr('keyframes'), q=True, valueChange=True, t=frame)
    if idx:
        return int(idx[0])
    else:
        return None

def key_exists_at_frame(frame):
    """
    Return true if a key is set at the given frame.
    """
    return _get_key_index_at_frame(frame) is not None

def find_frame_of_key(frame):
    """
    Return the nearest key on or before frame, or None if there aren't any.
    """
    keys = get_singleton(create=False)
    if keys is None:
        return None
    
    # Why is there no <= search?
    frames = pm.findKeyframe(keys.attr('keyframes'), t=frame + 0.000001, which='previous')
    if frames is None:
        return None
    if frames > frame:
        return None
    return frames

   
def get_all_keys():
    """
    Return the time and name index of all named keys.
    """
    keys = get_singleton(create=False)
    if keys is None:
        return {}

    time_and_index = pm.keyframe(keys.attr('keyframes'), q=True, valueChange=True, timeChange=True, absolute=True)

    # keyframe() returns floats, even though the index values are integers.  Convert them
    # to ints.
    time_and_index = {frame: int(idx) for frame, idx in time_and_index}
    return time_and_index

def get_all_names():
    """
    Return a dictionary of all names, indexed by index.
    """
    keys = get_singleton(create=False)
    if keys is None:
        return {}
    
    entries = keys.attr('entries')

    result = {}
    for entry in entries:
        idx = entry.index()
        result[idx] = entry.attr('name').get()
    return result

def get_name_at_idx(idx):
    """
    Return a single name.
    """
    if idx is None:
        return None

    keys = get_singleton(create=False)
    if keys is None:
        return None
    return keys.attr('entries').elementByLogicalIndex(idx).attr('name').get()

def get_name_at_frame(frame):
    idx = _get_key_index_at_frame(frame)
    if idx is None:
        return None

    return get_name_at_idx(idx)

def set_name_at_frame(frame, name):
    keys = get_singleton(False)
    if keys is None:
        return

    # Run index cleanup if needed before making changes to the frame.
    cleanup_duplicate_indices()    

    idx = _get_key_index_at_frame(frame)
    if idx is None:
        return

    attr = keys.attr('entries').elementByLogicalIndex(idx).attr('name')

    # Don't set the name if it isn't changing, so an undo entry isn't created.
    if attr.get() != name:
        attr.set(name)

def _get_unused_name_index():
    """
    Return the first unused index in the name list.
    """
    # Get the full key list, so we can find an unused slot.
    #
    # Note that we're looking at the entries actually referenced from keyframes and
    # not just calling get(mi=True) on entries, so we'll reuse stale entries.
    name_indices = get_all_keys().values()
    name_indices.sort()

    # Search for the first unused index.
    prev_idx = -1
    for idx in name_indices:
        if idx != prev_idx + 1:
            break
        prev_idx = idx
    return prev_idx + 1

   
def create_key_at_time(frame):
    """
    Create a key at the given time.  If a key already exists, return its index.
    """
    keys = get_singleton()
    
    # Find the name index for frame, if it already exists.
    idx = _get_key_index_at_frame(frame)
    if idx is not None:
        return idx

    # There's no key at the current frame.  Find an unused name index and create it.
    # We have to set the value, then set the keyframe.  If we just call setKeyframe,
    # the value won't be set correctly if it's in a character set.
    #
    # Disable auto-keyframe while we do this.  Otherwise, a keyframe will also
    # be added at the current frame (which seems like a bug).
    with maya_helpers.disable_auto_keyframe():
        idx = _get_unused_name_index()
        keys.attr('keyframes').set(idx)
        pm.setKeyframe(keys, at='keyframes', time=frame, value=idx)

    # setKeyframe can do this, but it's buggy: outTangentType='step' isn't applied if
    # we add a key before any other existing keys.
    pm.keyTangent(keys, time=frame, inTangentType='stepnext', outTangentType='step')

    # Keyframes can be deleted by the user, which leaves behind stale entries.  Remove
    # any leftover data in the slot we're using.
    pm.removeMultiInstance(keys.attr('entries').elementByLogicalIndex(idx))

    return idx

def delete_key_at_frame(frame):
    """
    Delete the key at frame.

    Note that we don't delete the underlying zKeyframeNaming node if it's empty, since it might
    be added to character sets by the user.
    """
    keys = get_singleton()

    # Run index cleanup if needed before making changes to the frame.
    cleanup_duplicate_indices()    

    all_keys = get_all_keys()

    idx = pm.keyframe(keys.attr('keyframes'), q=True, valueChange=True, t=frame)
    if not idx:
        return

    # Remove the keyframe and any associated data.
    pm.cutKey(keys.attr('keyframes'), t=frame)
    pm.removeMultiInstance(keys.attr('entries').elementByLogicalIndex(idx[0]))

_running_cleanup = False
def cleanup_duplicate_indices():
    """
    Clean up duplicate entries in the key index.

    If the user copies and pastes keyframe indices in the graph editor, we'll
    end up with multiple frames pointing at the same name entry.  If we edit
    those entries without cleaning it up first, we'll cause unwanted changes.
    """
    try:
        # Make sure that if we call other functions and they recurse back into here,
        # we don't run cleanup every time.
        global _running_cleanup
        if _running_cleanup:
            return
        _running_cleanup = True
        
        keys = get_singleton(create=False)
        if keys is None:
            return

        all_keys = get_all_keys()
        keys_by_index = defaultdict(list)
        for frame, index in all_keys.items():
            keys_by_index[index].append(frame)

        # We only care about indices that are used on more than one frame.
        # Sort frames, so we always leave the first one alone and adjust the rest.
        keys_by_index = {idx: sorted(frames) for idx, frames in keys_by_index.iteritems() if len(frames) >= 2}

        # Get the names for each frame we're correcting.
        names = {idx: get_name_at_idx(idx) for idx in keys_by_index.keys()}

        # Delete the duplicate keyframes.  Once we do this, we'll be back in a clean
        # state.
        for idx, frames in keys_by_index.items():
            for frame in frames[1:]:
                pm.cutKey(keys.attr('keyframes'), t=frame)

        # Create new keys at the frames we deleted, using the same name that it had previously.
        for idx, frames in keys_by_index.items():
            name = names[idx]
            for frame in frames[1:]:
                create_key_at_time(frame)
                set_name_at_frame(frame, name)
    finally:
        _running_cleanup = False

def connect_to_arnold():
    """
    If mtoa is loaded, attach the current frame name to a custom EXR attribute,
    so the frame name is exported with renders.
    """
    if not pm.pluginInfo('mtoa', q=True, loaded=True):
        log.warning('The Arnold plugin isn\'t loaded.')
        return

    # Find the Arnold driver node, if it exists.
    driver = pm.ls('defaultArnoldDriver')
    if not driver:
        log.warning('The Arnold driver doesn\'t exist.  Select Arnold as the scene renderer first.')
        return

    driver = driver[0]

    # Get the output attribute.
    keys = get_singleton()
    output = keys.attr('arnoldAttributeOut')

    # Get Arnold's array of custom attributes.
    attrs = driver.attr('customAttributes')

    # See if the output attribute is already connected to a custom attribute, so we
    # don't create it more than once.
    for conn in output.listConnections(s=False, d=True, p=True):
        if not conn.isElement():
            continue
        if conn.array() == attrs:
            log.info('An Arnold attribute has already been created.')
            return
    
    # Connect it to the next unused EXR attribute.
    idx = pm.mel.eval('getNextFreeMultiIndex %s 0' % attrs)
    input = attrs.elementByLogicalIndex(idx)
    output.connect(input)
    log.info('Arnold attribute created.')

def select_naming_node():
    node = get_singleton(create=True)
    pm.select(node)

class KeyframeNamingWindow(MayaQWidgetDockableMixin, Qt.QDialog):
    def __init__(self):
        super(KeyframeNamingWindow, self).__init__()

        # How do we make our window handle global hotkeys?
#        undo = Qt.QAction('Undo', self)
#        undo.setShortcut(Qt.Qt.CTRL + Qt.Qt.Key_Z)
#        undo.triggered.connect(lambda: pm.undo())
#        self.addAction(undo)

#        redo = Qt.QAction('Redo', self)
#        redo.setShortcut(Qt.Qt.CTRL + Qt.Qt.Key_Y)
#        redo.triggered.connect(lambda: pm.redo(redo=True))
#        self.addAction(redo)

        self.shown = False
        self.callback_ids = om.MCallbackIdArray()
        self._reregister_callback_queued = False

        self.frames_in_list = []
        self._currently_refreshing = False
        self._currently_setting_selection = False
        self._listening_to_singleton = None
        self._listening_to_anim_curve = None

        self.time_change_listener = maya_helpers.TimeChangeListener(self._time_changed)

        # Make sure zKeyframeNaming has been generated.
        qt_helpers.compile_all_layouts()

        from qt_generated import keyframe_naming
        reload(keyframe_naming)

        self._ui = keyframe_naming.Ui_keyframe_naming()
        self._ui.setupUi(self)

        self._ui.removeFrame.clicked.connect(self.delete_selected_frame)
        self._ui.renameFrame.clicked.connect(self.rename_selected_frame)
        self._ui.addFrame.clicked.connect(self.add_new_frame)
        self._ui.frameList.itemDelegate().commitData.connect(self.frame_name_edited)
        self._ui.frameList.itemDelegate().closeEditor.connect(self.name_editor_closed)
        self._ui.frameList.itemSelectionChanged.connect(self.selected_frame_changed)
        self._ui.frameList.itemClicked.connect(self.selected_frame_changed)
        self._ui.frameList.setContextMenuPolicy(Qt.Qt.CustomContextMenu)

        def context_menu(pos):
            # Activate the context menu for the selected item.
            item = self._ui.frameList.itemAt(pos)
            if item is None:
                return

            keyframe_context_menu = self._create_keyframe_context_menu(item)
            action = keyframe_context_menu.exec_(self._ui.frameList.mapToGlobal(pos))
            
        self._ui.frameList.customContextMenuRequested.connect(context_menu)

        # Create the menu.  Why can't this be done in the designer?
        menu_bar = Qt.QMenuBar()
        self.layout().setMenuBar(menu_bar)

        edit_menu = menu_bar.addMenu('Edit')
        menu_select_naming_node = Qt.QAction('Select zKeyframeNaming node', self)
        menu_select_naming_node.setStatusTip('Select the zKeyframeNaming node, to edit keyframes in the graph editor')
        menu_select_naming_node.triggered.connect(select_naming_node)
        edit_menu.addAction(menu_select_naming_node)
        
        add_arnold_attribute = Qt.QAction('Add Arnold attribute', self)
        add_arnold_attribute.setStatusTip('Add a custom Arnold attribute to export the current frame name to rendered EXR files')
        add_arnold_attribute.triggered.connect(connect_to_arnold)
        edit_menu.addAction(add_arnold_attribute)

        self.installEventFilter(self)
        self._ui.frameList.installEventFilter(self)

        # showEvent() will be called when we're actually displayed, and fill in the list.

    def eventFilter(self, object, event):
        if object is self:
            if event.type() == Qt.QEvent.KeyPress:
                if event.key() == Qt.Qt.Key_Delete:
                    self.delete_selected_frame()
                    return True
                elif event.key() == Qt.Qt.Key_Insert:
                    self.add_new_frame()
                    return True
        elif object is self._ui.frameList:
            if event.type() == Qt.QEvent.KeyPress:
                if event.key() == Qt.Qt.Key_Return:
                    self.rename_selected_frame()

        return super(KeyframeNamingWindow, self).eventFilter(object, event)

    def done(self, result):
        """
        This is called when the window is closed.
        """
        self.close()
        super(MayaQWidgetDockableMixin, self).done(result)

    def get_selected_frame_item(self):
        """
        Return the QListWidgetItem for the frame selected in the list, or None if
        nothing is selected.
        """
        selection = self._ui.frameList.selectedItems()
        if not selection:
            return None

        return selection[0]

    def selected_frame_changed(self):
        """
        Set the scene time to the selected frame.
        """
        # If self.set_selected_frame is setting the selection, don't change the scene time.
        if self._currently_setting_selection:
            return

        selection = self.get_selected_frame_item()
        if not selection:
            return

        pm.currentTime(selection.frame)
       
    def set_selected_frame(self, frame):
        """
        Set the selected frame in the list.
        """
        # Binary search for the nearest frame on or before frame.
        idx = max(bisect.bisect_right(self.frames_in_list, frame) - 1, 0)
        if idx >= self._ui.frameList.count():
            return

        item = self._ui.frameList.item(idx)

        # Let selected_frame_changed know that we're setting the selection explicitly, so
        # it shouldn't sync the scene time up with it.
        self._currently_setting_selection = True
        try:
            self._ui.frameList.setCurrentItem(item)
        finally:
            self._currently_setting_selection = False

    def set_selected_frame_from_current_time(self):
        """
        Select the frame in the list from the current time.
        """
        self.set_selected_frame(pm.currentTime(q=True))

    def cancel_rename(self):
        """
        If an entry is being renamed, cancel it.
        """
        if self._ui.frameList.state() != Qt.QAbstractItemView.EditingState:
            return

        item = self.get_selected_frame_item()
        self._ui.frameList.closePersistentEditor(item)

    def _create_keyframe_context_menu(self, item):
        keyframe_context_menu = Qt.QMenu()
        time_slider_start = keyframe_context_menu.addAction('Set time slider start')
        time_slider_start.triggered.connect(lambda: pm.playbackOptions(min=item.frame))

        time_slider_end = keyframe_context_menu.addAction('Set time slider end')
        time_slider_end.triggered.connect(lambda: pm.playbackOptions(max=item.frame))

        time_render_start = keyframe_context_menu.addAction('Set render start')
        time_render_start.triggered.connect(lambda: pm.PyNode('defaultRenderGlobals').startFrame.set(item.frame))

        time_render_end = keyframe_context_menu.addAction('Set render end')
        time_render_end.triggered.connect(lambda: pm.PyNode('defaultRenderGlobals').endFrame.set(item.frame))

        return keyframe_context_menu

    def add_new_frame(self):
        """
        Create a key if one doesn't exist already, and begin editing its name.
        """
        with maya_helpers.undo('Create named keyframe'):
            # If we're editing, cancel editing before adding the new frame, or the
            # new frame won't be visible.  This can happen if you select a frame,
            # click Add, then select another frame and click Add without first
            # pressing enter for the first rename.  This usually only happens if
            # the window is docked into the main Maya window.
            self.cancel_rename()

            if not key_exists_at_frame(pm.currentTime(q=True)):
                frame = pm.currentTime(q=True)
                create_key_at_time(frame)
                set_name_at_frame(frame, 'Frame %i' % frame)
                
            # Our listeners will refresh automatically, but that won't happen until later.  Refresh
            # immediately, so we can initiate editing on the new item.
            self.refresh()

            # Find the new item and edit it to let the user set its name.
            self.rename_selected_frame()

    def delete_selected_frame(self):
        """
        Delete the frame that's selected in the list, if any.
        """
        item = self.get_selected_frame_item()
        if item is None:
            return

        self.cancel_rename()
        with maya_helpers.undo('Delete keyframe bookmark'):
            delete_key_at_frame(item.frame)
    
    def rename_selected_frame(self):
        """
        Rename the frame selected in the list, if any.
        """
        selection = self.get_selected_frame_item()
        if not selection:
            return

        self._ui.frameList.editItem(selection)

    def refresh(self):
        if not self.shown:
            return

        # Don't refresh while editing.
        if self._ui.frameList.state() == Qt.QAbstractItemView.EditingState:
            return

        self._currently_refreshing = True
        try:
            all_keys = get_all_keys()
            all_names = get_all_names()
            self._ui.frameList.clear()
            self.frames_in_list = []

            # Add keys in chronological order.
            for frame in sorted(all_keys.keys()):
                idx = all_keys[frame]
                name = all_names.get(idx, '')
                item = Qt.QListWidgetItem(name)
                item.frame = frame
                item.setFlags(item.flags() | Qt.Qt.ItemIsEditable)

                self._ui.frameList.addItem(item)

                self.frames_in_list.append(frame)

            self.set_selected_frame_from_current_time()
        finally:
            self._currently_refreshing = False

    def _time_changed(self):
        """
        When the scene time changes, update the current selection to match.

        This isn't called during playback.
        """
        qt_helpers.run_async_once(self.set_selected_frame_from_current_time)

    def _register_listeners(self):
        # Stop if we've already registered listeners.
        if self.callback_ids.length():
            return

        msg = om.MDGMessage()
        self.callback_ids.append(msg.addNodeAddedCallback(self._keyframe_naming_nodes_changed, 'zKeyframeNaming', None))
        self.callback_ids.append(msg.addNodeRemovedCallback(self._keyframe_naming_nodes_changed, 'zKeyframeNaming', None))
        node = get_singleton(create=False)

        if node is not None:
            self.callback_ids.append(om.MNodeMessage.addNameChangedCallback(node.__apimobject__(), self._node_renamed))
            self.callback_ids.append(om.MNodeMessage.addAttributeChangedCallback(node.__apimobject__(), self._singleton_node_changed, None))
            self._listening_to_singleton = node

            anim_curve = self._get_keyframe_anim_curve()
            self._listening_to_anim_curve = anim_curve

            # If the keyframes attribute is animated, listen for keyframe changes.
            if anim_curve is not None:
                self.callback_ids.append(oma.MAnimMessage.addNodeAnimKeyframeEditedCallback(anim_curve, self._keyframe_keys_changed))

        self.time_change_listener.register()

    def _unregister_listeners(self):
        if self.callback_ids:
            # Why is the unregistering API completely different from the registering API?
            msg = om.MMessage()
            msg.removeCallbacks(self.callback_ids)
            self.callback_ids.clear()

        self.time_change_listener.unregister()
        self._listening_to_singleton = None
        self._listening_to_anim_curve = None

    def _keyframe_keys_changed(self, *args):
        self._async_refresh()

    def _keyframe_naming_nodes_changed(self, node, data):
        """
        A zKeyframeNaming node was created or deleted.  See if we need to update
        our listeners, and refresh the UI.
        """
        # Queue this instead of doing it now, since node removed callbacks happen
        # before the node is actually deleted.
        self._async_check_listeners()

    def _node_renamed(self, node, old_name, unused):
        """
        A zKeyframeNaming node was renamed.  Refresh the node list if it's a zKeyframeNaming node.

        Note that we only listen to see if a known node was renamed, which means we'll notice
        if a zKeyframeNaming node is renamed away from the singleton, but not if it's renamed
        back.  To see those, we'd need to listen to all renames in the scene, which would cause
        a performance hit for a very rare edge case.  Unlike MDGMessage, MNodeMessage doesn't
        let us filter by node type.
        """
        self._async_check_listeners()

    @classmethod
    def _get_keyframe_anim_curve(cls):
        """
        Return the animCurve node controlling keyframes, or None if keyframes
        isn't animated.

        A raw MObject is returned.
        """
        keys = get_singleton(create=False)
        if keys is None:
            return None

        result = om.MObjectArray()
        oma.MAnimUtil.findAnimation(keys.attr('keyframes').__apimplug__(), result)
        if result.length() == 0:
            return None
        else:
            #return pm.PyNode(result[0])
            return result[0]

    # isOpeningFile is true while opening a file, but not while loading a reference.
    # isReadingFile is true while loading references, but not while loading files.
    @staticmethod
    def in_file_io():
        return om.MFileIO.isOpeningFile() or om.MFileIO.isReadingFile() or  \
            om.MFileIO.isWritingFile() or om.MFileIO.isNewingFile() or \
            om.MFileIO.isImportingFile()


    def _check_listeners(self):
        """
        This is called when our zKeyframeNaming node or its singleton may have changed.
        Check if we need to reestablish listeners with the new nodes, and refresh the
        UI.
        """
        # We should have our listeners registered if we're visible and we're not
        # in the middle of file I/O.
        in_file_io = self.in_file_io()
        should_be_listening = self.shown and not in_file_io
        if not should_be_listening:
            # If we're listening, stop.
            self._unregister_listeners()

            # If we're in file I/O, we want to reestablish listeners once the operation
            # completes.  Queue a job to come back here and recheck during idle (if
            # we don't already have one waiting).
            if in_file_io and not self._reregister_callback_queued:
                def reestablish_callbacks():
                    self._reregister_callback_queued = False
                    self._check_listeners()

                qt_helpers.run_async_once(reestablish_callbacks)
                self._reregister_callback_queued = True
            
            # If we're not listening anyway, 
            return

        # We do want to be listening.
        #
        # If a keyframe node is connected or disconnected from zKeyframeNaming.keyframes,
        # we need to reestablish listeners to listen for keyframe changes.
        #
        # There's no obvious quick way to find out if this connection affects that, though.
        # We can't just look at the plugs, since there might be other nodes in between, like
        # character sets.  Instead, we have to look at the actual animation curve node and
        # see if it's changed.
        singleton = get_singleton(create=False)
        anim_curve = self._get_keyframe_anim_curve()
        if singleton is not self._listening_to_singleton or anim_curve is not self._listening_to_anim_curve:
            # One of our nodes have changed.
            self._unregister_listeners()

        # If we're (still) listening, then we're done.
        if self.callback_ids.length():
            return

        # Register our listeners.
        self._register_listeners()

        # Since we weren't listening, the UI may be out of date and should be refreshed.
        self.refresh()
        
    def _async_check_listeners(self):
        qt_helpers.run_async_once(self._check_listeners)
        
    def _singleton_node_changed(self, msg, plug, otherPlug, data):
        # For some reason, this is called once per output, but not actually called for changed inputs.
        # It seems to not notice when a value has changed because its input key connection has changed.
        #
        # kAttributeSet is sent for most things, like moving the time slider causing the current key
        # to change and us making changes directly.  kAttributeEval catches some things that doesn't,
        # in particular editing keys with the graph editor, but this only works if something is connected
        # to the output to trigger an evaluation.  Note that Set usually comes from the main thread, but
        # Eval tends to come from a worker thread, so we depend on the async dispatching to move this to
        # the main thread.
        if msg & (
                om.MNodeMessage.kConnectionMade |
                om.MNodeMessage.kConnectionBroken |
                om.MNodeMessage.kAttributeSet |
                om.MNodeMessage.kAttributeEval):
            # kConnectionMade and kConnectionBroken will tell us when we've been connected
            # or disconnected and should refresh our listeners in case we have a new animCurve.
            #
            # However, they're not sent if we're already connected to a character set and the
            # character set gets connected to an animCurve, or any other in-between
            # proxy of animCurves (the time editor does this as well).  We could detect
            # this with MDGMessage.addConnectionCallback, but that's called on every
            # connection change in the scene, which is too slow when things like render
            # setups are making wide-scale changes to the scene.
            #
            # Most of the time a new animCurve is connected, it'll change the current value,
            # which will cause kAttributeSet or kAttributeEval to be sent.
            qt_helpers.run_async_once(self._check_listeners)

    def _async_refresh(self):
        """
        Queue a refresh.  If this is called multiple times before we do the refresh, we'll only
        refresh once.
        """
        qt_helpers.run_async_once(self.refresh)

    def frame_name_edited(self, widget):
        # How do you find out which item was edited?  QT's documentation is useless.
        items = self._ui.frameList.selectedItems()
        if not items:
            return
        item = items[0]

        with maya_helpers.undo('Rename keyframe bookmark'):
            set_name_at_frame(item.frame, item.text())

    def name_editor_closed(self, editor, hint):
        # We don't refresh while editing, so we don't clobber the user's edits.  Refresh
        # after editing finishes.
        self.refresh()

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        self._unregister_listeners()

    def showEvent(self, event):
        # Why is there no isShown()?
        if self.shown:
            return
        self.shown = True

        # Refresh when we're displayed.
        self._async_check_listeners()

        super(KeyframeNamingWindow, self).showEvent(event)

    def hideEvent(self, event):
        if not self.shown:
            return
        self.shown = False

        # Refresh when we're hidden.
        self._async_check_listeners()

        super(KeyframeNamingWindow, self).hideEvent(event)

    def dockCloseEventTriggered(self):
        # Bug workaround: closing the dialog by clicking X doesn't call closeEvent.
        self.cleanup()
    
    def close(self):
        self.cleanup()
        super(KeyframeNamingWindow, self).close()

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()
        self._ui = None

    def _open_ui(self, restore):
        if restore:
            # We're being reopened, and a layout has already been created.
            restored_control = omui.MQtUtil.getCurrentParent()

        if self._ui is None:
            self._ui = KeyframeNamingWindow()
            def closed():
                self._ui = None
            self._ui.destroyed.connect(closed)

        if restore:
            # We're restoring into an existing layout.  Just add the control that was created
            # for us, and show() will be called automatically.
            ptr = omui.MQtUtil.findControl(self._ui.objectName())
            omui.MQtUtil.addWidgetToMayaLayout(long(ptr), long(restored_control))
        else:
            # Disable retain, or we won't be able to create the window again after reloading the script
            # with an "Object's name 'DialogWorkspaceControl' is not unique" error.
            #
            # Watch out: this function has *args and *kwargs which should be there, which causes it to
            # silently eat unknown parameters instead of throwing an error.
            self._ui.setDockableParameters(dockable=True, retain=False,
                plugins='zKeyframeNaming.py',
                uiScript='import zMayaTools.keyframe_naming; zMayaTools.keyframe_naming.menu.restore()'
            )

            # If we just set plugins (which is really workspaceControl -requiredPlugin), the control
            # will be closed on launch.  We need to enable checksPlugins too to work around this.
            control_name = self._ui.objectName() + 'WorkspaceControl'
            pm.workspaceControl(control_name, e=True, checksPlugins=True)

            self._ui.show()

    def show(self):
        """
        Show the UI.
        """
        self._open_ui(restore=False)
        
    def hide(self):
        """
        Hide the UI.
        """
        if self._ui is not None:
            self._ui.hide()
        
    def restore(self):
        """
        This is called by Maya via uiScript when a layout is restored.
        """
        self._open_ui(True)

    def add_menu_items(self):
        menu = 'MayaWindow|mainKeysMenu'

        # Make sure the menu is built.
        pm.mel.eval('AniKeyMenu "%s";' % menu)

        def show_window(unused):
            self.show()

        menu_items = pm.menu(menu, q=True, ia=True)
        section = self.find_menu_section_by_name(menu_items, 'Edit')
        self.add_menu_item('zMayaTools_zKeyframeNaming', label='Keyframe Bookmarks', parent=menu, insertAfter=section[-1],
                command=lambda unused: self.show())

    def remove_menu_items(self):
        super(PluginMenu, self).remove_menu_items()

        if self._ui is None:
            return

        # If the keying window is open when the module is unloaded, close it.
        self._ui.close()
        self._ui = None

menu = PluginMenu()

