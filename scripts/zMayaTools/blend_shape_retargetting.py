import math, inspect, os, sys, time
import pymel.core as pm
import maya.cmds as cmds
from zMayaTools.menus import Menu
from zMayaTools import maya_logging, maya_helpers

log = maya_logging.get_log()

# Notes:
#
# - This doesn't handle inbetween targets.  There's no good way to export those to
# use them with game engines, so I don't use them.
# - The source and destination blend shapes should have one target each.  Multi-target
# blend shapes aren't supported.
# - If you request a retargetted blend shape, one will always be created.  We don't
# check to see if the source blend shape actually has any effect on the target, so if
# you retarget an elbow corrective on the body to the shoes, it'll just create an empty
# target.  That's harmless, and checking if the mesh has actually changed would be
# slower.
#
# A "set" button to set the selection to the source or destination blend shape
# would be nice, as well as a "swap" button, but Maya's GUI system is so awful
# to use I just don't want to figure out how to make a clean UI for it.
 
def duplicate_mesh_from_plug(shape_attr, name):
    """
    Given a deformed mesh, create a new mesh that's a clean copy of its base mesh.
    Return the transform.
    """
    # Create a new mesh, and copy the base mesh of src_node.
    transform_node = pm.createNode('transform', n=name)

    # Copy the mesh.
    mesh_node = pm.createNode('mesh', n=name + 'OrigShape', p=transform_node)
    shape_attr.connect(mesh_node.attr('inMesh'))

    # Access vertex data on the copy, to force the data to copy.  Otherwise it won't be copied, since
    # we're disconnecting it before the display will refresh.
    transform_node.vtx[0]
    shape_attr.disconnect(mesh_node.attr('inMesh'))

    return transform_node
    
def duplicate_base_mesh(node):
    """
    Given a deformed mesh, create a new mesh that's a clean copy of its base mesh.
    Return the transform.
    """
    # Create a new mesh, and copy the base mesh of src_node.
    transform_node = duplicate_mesh_from_plug(node.getShapes()[-1].attr('worldMesh[0]'), name=node.nodeName() + 'Copy')

    # Copy the world space transform.
    pm.xform(transform_node, ws=True, matrix=pm.xform(node, q=True, ws=True, matrix=True))

    return transform_node
 
#def attach_deformer(mesh, deformer_node):
#    """
#    Given a shape and a deformer node, attach the deformer to the shape.
#
#    Maya does this when yo ucreate a mesh with pm.deformer, but not if 
#    Given a transform node with a shape, 
#    """
#    group_parts = pm.createNode('groupParts')
#    group_parts.attr('inputComponents').set(1, 'vtx[*]', type='componentList')
#    group_parts.attr('ihi').set(False)
#    mesh.attr('worldMesh[0]').connect(group_parts.attr('inputGeometry'))
#
#    group_id = pm.createNode('groupId')
#    group_id.attr('groupId').connect(group_parts.attr('groupId'))
#    group_id.attr('ihi').set(False)
#
#    group_parts.attr('outputGeometry').connect(deformer_node.attr('input[0]').attr('inputGeometry'))
#    group_id.attr('groupId').connect(deformer_node.attr('input[0]').attr('groupId'))
#
#    src_mesh_output = pm.createNode('mesh', n=mesh.getTransform().nodeName() + 'CopyShape', p=mesh.getTransform())
#    deformer_node.attr('outputGeometry[0]').connect(src_mesh_output.attr('inMesh'))
#    mesh.attr('intermediateObject').set(1)

def prep_for_retargetting(blend_shape, restores):
    """
    Prepare blend_shape for being used as the source for retargetting.

    - We need to be able to set blend shape weights, so disconnect anything connected
    to all weights.
    - Make sure all weights and groups are visible, and all groups have a weight of 1, so
    # they don't prevent us from enabling weights.
    - Set all blend shape weights to 0, so we can enable them one at a time.

    Changes will be added to restores, so they'll be reverted by maya_helpers.restores()
    when we're done.
    """
    # Make sure the blendShape itself is turned on.
    restores.append(maya_helpers.SetAndRestoreAttr(blend_shape.envelope, 1))
    
    for directory_entry in blend_shape.targetDirectory:
        restores.append(maya_helpers.SetAndRestoreAttr(directory_entry.directoryVisibility, 1))

        # Setting directoryParentVisibility will ensure that the directory isn't hidden from its
        # parent being hidden, or from a blendShape group on the shapeEditorManager being hidden.
        restores.append(maya_helpers.SetAndRestoreAttr(directory_entry.directoryParentVisibility, 1))

        restores.append(maya_helpers.SetAndRestoreAttr(directory_entry.directoryWeight, 1))

    for target_visibility in blend_shape.targetVisibility:
        print target_visibility
        restores.append(maya_helpers.SetAndRestoreAttr(target_visibility, 1))

    # XXX: untested
    for inbetween_info_group in blend_shape.inbetweenInfoGroup:
        for inbetween_info in inbetween_info_group.inbetweenInfo:
            restores.append(maya_helpers.SetAndRestoreAttr(inbetween_info.inbetweenVisibility, 1))

    for weight in blend_shape.weight:
        # This will also disconnect anything connected to the weight.
        restores.append(maya_helpers.SetAndRestoreAttr(weight, 0))

def redst_blend_shapes(src_node, dst_node, src_blend_shape_node, dst_blend_shape_node, blend_shape_indices, connect_weights):
    try:
        pm.waitCursor(state=True)

        # Remember the selection, so we can restore it.
        old_selection = pm.ls(sl=True)

        # Create a temporary namespace to work in.  This lets us clean up when we're done by just deleting
        # the whole namespace.
        old_namespace = pm.namespaceInfo(currentNamespace=True)
        pm.namespace(add='temp')
        pm.namespace(setNamespace='temp')

        with maya_helpers.restores() as restores:
            prep_for_retargetting(src_blend_shape_node, restores)
            src_to_dst_weights = redst_blend_shapes_inner(src_node, dst_node, src_blend_shape_node, dst_blend_shape_node, blend_shape_indices)

        # Copy or connect weights.  Do this after we finish the above, since we need to let maya_helpers.restores()
        # restore the original weights before we copy them, or they'll all be set to 0.
        for src_weight, dst_weight in src_to_dst_weights.items():
            if connect_weights:
                # Connect the source blend shape's weight to the target.
                src_weight.connect(dst_weight)
            else:
                # Copy the source weight.
                dst_weight.set(src_weight.get())

        return src_to_dst_weights
    finally:
        pm.waitCursor(state=False)

        # Delete the temporary namespace.
        pm.namespace(setNamespace=old_namespace)
        pm.namespace(rm=':temp', deleteNamespaceContent=True)

        pm.select(old_selection)

def add_blend_shape_index_to_directory(directory_entry, idx):
    """
    Add idx to a blendShape.targetDirectory child list if it's not already present, and
    remove it from all other directories.
    """
    # Add idx to directory_entry.
    child_indices = directory_entry.childIndices.get() or []
    if idx not in child_indices:
        child_indices.append(idx)
        directory_entry.childIndices.set(child_indices, type='Int32Array')

    # Remove idx from all others.
    for other_directory_entry in directory_entry.array():
        if other_directory_entry == directory_entry:
            continue

        child_indices = other_directory_entry.childIndices.get() or []
        if idx in child_indices:
            child_indices.remove(idx)
            other_directory_entry.childIndices.set(child_indices, type='Int32Array')

    if idx >= 0:
        # For blend shape targets, set parentDirectory to match.
        directory_entry.node().parentDirectory[idx].set(directory_entry.index())

def find_blend_shape_directory_by_blend_shape_idx(blend_shape, idx):
    """
    Find the target directory of the given blend shape index.

    If it's not found, return the root directory.
    """
    for directory in blend_shape.targetDirectory:
        # childIndices will be None if there are no entries.
        if idx in (directory.childIndices.get() or []):
            return directory

    # If we can't find it, return the root directory.
    return blend_shape.targetDirectory[0]

def find_directory_entry_by_name(blend_shape, name):
    """
    Find and return the targetDirectory with the given name, or None if it doesn't exist.
    """
    for directory_entry in blend_shape.targetDirectory:
        if directory_entry.directoryName.get() == name:
            return directory_entry
    return None

def recursively_create_hierarchy(src_directory_entry, dst_blend_shape):
    """
    Create a matching blend shape directory hierarchy for dst_directory_entry in
    dst_blend_shape.
    
    Return the corresponding targetDirectory in the destination blendShape node.
    """
    # If this is the root, stop.
    if src_directory_entry.index() == 0:
        return dst_blend_shape.targetDirectory[0]

    # Recursively create the parent.  dst_directory_parent is the target directory of the parent.
    parent_index = src_directory_entry.parentIndex.get()
    parent_directory = src_directory_entry.array()[parent_index]
    dst_directory_parent = recursively_create_hierarchy(parent_directory, dst_blend_shape)

    # If a directory with the same name already exists in dst_blend_shape, use it.
    dst_directory_entry = find_directory_entry_by_name(dst_blend_shape, src_directory_entry.directoryName.get())
    if dst_directory_entry is not None:
        return dst_directory_entry

    # Create the directory, copying attributes from the source.
    new_shape_directory_index = max(dst_blend_shape.targetDirectory.get(mi=True)) + 1
    dst_directory_entry = dst_blend_shape.targetDirectory[new_shape_directory_index]
    dst_directory_entry.directoryName.set(src_directory_entry.directoryName.get())
    dst_directory_entry.directoryVisibility.set(dst_directory_parent.directoryVisibility.get())
    dst_directory_entry.directoryParentVisibility.set(dst_directory_parent.directoryParentVisibility.get())
    dst_directory_entry.directoryWeight.set(dst_directory_parent.directoryWeight.get())
    dst_directory_entry.parentIndex.set(dst_directory_parent.index())

    # Add the new directory to the childIndices list of the parent.  Groups are stored as
    # the inverse of their index.  (Do this even if we're not newly creating the directory to
    # make sure it's present, but use the existing directory index.)
    add_blend_shape_index_to_directory(dst_directory_parent, -dst_directory_entry.index())

    return dst_directory_entry

def create_matching_blend_shape_directory(src_blend_shape, src_blend_shape_index, dst_blend_shape, dst_blend_shape_index):
    """
    Create a blend shape directory hierarchy in dst_blend_shape for dst_blend_shape_index,
    matching the grouping of src_blend_shape_index in src_blend_shape, and add
    dst_blend_shape_index to it.
    """
    # Find the target directory for the source blend shape.
    src_directory = find_blend_shape_directory_by_blend_shape_idx(src_blend_shape, src_blend_shape_index)

    # Create the directory hierarchy, and move the blend shape into it.
    dst_directory_entry = recursively_create_hierarchy(src_directory, dst_blend_shape)
    add_blend_shape_index_to_directory(dst_directory_entry, dst_blend_shape_index)

def redst_blend_shapes_inner(src_node, dst_node, src_blend_shape_node, dst_blend_shape_node, blend_shape_indices):
    # Duplicate the destination mesh.
    dst_node_copy = duplicate_base_mesh(dst_node)

    # Wrap dst_node_copy to src_node, so the destination mesh follows blend shapes on the source mesh.
    wrap_deformer(src_node, dst_node_copy, auto_weight_threshold=True, falloff_mode=0, use_cvwrap_if_available=True)

    # Find all blend shape names.  We require that blend shapes have a name, and always give
    # blend shapes the same name as their source.
    dst_blend_shape_name_to_index = {}
    for idx in dst_blend_shape_node.weightIndexList():
        src_weight = dst_blend_shape_node.attr('w').elementByLogicalIndex(idx)
        target_name = pm.aliasAttr(src_weight, q=True)
        
        if target_name is None:
            log.warning('Warning: destination blend shape has an unused blend shape %i' % idx)
            continue
        
        dst_blend_shape_name_to_index[target_name] = idx

    def get_unused_blend_shape_index(preferred_idx):
        # Return an index that isn't in use in dst_blend_shape_name_to_index.
        index_list = sorted(dst_blend_shape_name_to_index.values())
        if preferred_idx not in index_list:
            return preferred_idx

        for idx in xrange(0, len(index_list)+1):
            if idx not in index_list:
                return idx
        raise RuntimeError('Not reachable')

    # Do the actual retargetting.
    src_to_dst_weights = {}
    for idx in blend_shape_indices:
        # Make sure that we aren't connected backwards, or this would create a cycle.
        src_weight = src_blend_shape_node.attr('weight').elementByLogicalIndex(idx)

        # Each index is a weight attribute on the source blend shape deformer.  Get the name of the blend shape.
        target_name = pm.aliasAttr(src_weight, q=True)
        if target_name is None:
            log.warning('Error: blend shape index %i has no name' % idx)
            continue

        # Find the blend shape in the target with this name.  If it already exists, we'll just update
        # it.  Otherwise, we'll pick a new index and create a new one.
        new_idx = dst_blend_shape_name_to_index.get(target_name)
        if new_idx is None:
            # There's no existing blend shape by this name.  Find an unused one, and record that we've
            # used it.
            #
            # If it's available, use the same blend shape index, so the new blendShape deformer is compatible
            # with the old one in reference edits.
            new_idx = get_unused_blend_shape_index(preferred_idx=idx)
            dst_blend_shape_name_to_index[target_name] = new_idx

        dst_weight = dst_blend_shape_node.attr('weight').elementByLogicalIndex(new_idx)
        if dst_weight.isConnectedTo(src_weight):
            log.warning('Warning: the destination target %s is a source for the source %s.  Are the blend shapes selected backwards?' % (
                    dst_weight, src_weight))
            continue

        # Enable the blend shape target on the source object.  This will deform dst_node_copy through
        # the wrap deformer.
        weight = src_blend_shape_node.attr('w').elementByLogicalIndex(idx)
        weight.set(1)

        # Duplicate dst_node_copy in its deformed state.
        new_blend_shape_target = pm.duplicate(dst_node_copy, n='DeformedTarget')[0]

        # Disconnect the source weight from the destination weight before updating the blend shape
        # weight, or it'll print an unexplained "Problems occurred with dependency graph setup".
        # (Come on, guys, "there were problems" isn't an error message.)
        if src_weight.isConnectedTo(dst_weight):
            src_weight.disconnect(dst_weight)

        # Set the blend shape.
        pm.blendShape(dst_blend_shape_node, e=True, t=(dst_node, new_idx, new_blend_shape_target, 1.0))

        # Rename the blend shape target to match the source.  Don't do this if we have no
        # alias, since that causes a crash.
        if target_name:
            old_alias = pm.aliasAttr(dst_weight, q=True)
            pm.aliasAttr(dst_blend_shape_node.attr(old_alias), rm=True)
            pm.aliasAttr(target_name, dst_weight)

        # Disable the target.
        weight.set(0)

        # Create a matching blend shape directory, and add the new blend shape to it.
        create_matching_blend_shape_directory(src_blend_shape_node, idx, dst_blend_shape_node, new_idx)

        # We don't need the copied target.  Once we delete this, the blend shape will be baked into
        # the deformer.
        pm.delete(new_blend_shape_target)

        src_to_dst_weights[src_weight] = dst_weight

    return src_to_dst_weights

def _create_wrap(control_object, target,
        threshold=0,
        max_distance=0,
        influence_type=2, # 1 for point, 2 for face
        exclusive=False,
        auto_weight_threshold=False,
        falloff_mode=0): # 0 for volume, 1 for surface
    old_selection = pm.ls(sl=True)

    pm.select(target)
    pm.select(control_object, add=True)

    cmd = 'doWrapArgList "7" { "1", "%(threshold)s", "%(max_distance)s", "%(influence_type)s", "%(exclusive)s", "%(auto_weight_threshold)s",  ' \
            '"%(render_influences)s", "%(falloff_mode)s" };' % {
        'threshold': threshold,
        'max_distance': max_distance,
        'influence_type': influence_type,
        'exclusive': 1 if exclusive else 0,
        'auto_weight_threshold': 1 if auto_weight_threshold else 0,
        'render_influences': 1, # Never set this to 0.
        'falloff_mode': falloff_mode,
    }

    deformer_node = pm.mel.eval(cmd)[0]

    # Restore the old selection.
    pm.select(old_selection)

    return pm.PyNode(deformer_node)

def _create_cvwrap(control_object, target):
    """
    Create a wrap deformer with cvwrap, if available.  If the cvwrap plugin isn't available,
    return None.
    """
    if not maya_helpers.load_plugin('cvwrap.mll', required=False):
        return None

    old_selection = pm.ls(sl=True)

    pm.select(target)
    pm.select(control_object, add=True)
    deformer_node = cmds.cvWrap()

    # Restore the old selection.
    pm.select(old_selection)

    return pm.PyNode(deformer_node)

def wrap_deformer(control_mesh, target,
        use_cvwrap_if_available=False,
        threshold=0,
        max_distance=0,
        influence_type=2, # 1 for point, 2 for face
        exclusive=False,
        auto_weight_threshold=False,
        falloff_mode=0): # 0 for volume, 1 for surface
    # If any nodes are meshes, move up to the transform.
    selection = target.getParent() if target.nodeType() == 'mesh' else target

    control_transform = control_mesh.getParent() if control_mesh.nodeType() == 'mesh' else control_mesh

    deformer_node = None
    if use_cvwrap_if_available:
        deformer_node = _create_cvwrap(control_transform, selection)
        if deformer_node is None:
            log.warning('The cvwrap plugin isn\'t available.')

    if deformer_node is None:
        deformer_node = _create_wrap(control_transform, selection, threshold, max_distance, influence_type,
            exclusive, auto_weight_threshold, falloff_mode)

    return deformer_node

def copy_attr(src_attr, dst_attr):
    """
    Copying attributes is tricky.  If we just attr.set(attr2.get()), it'll be very slow
    since PyMel is very inefficient at large data sets.  Using cmds instead introduces
    new problems: we can't set large data sets all at once with it, so we'd have to break
    it apart.  Instead, use MPlug.getSetAttrCmds to get the commands that would be used to
    set up the node in an .MA file, and run them on our copy.
    """
    # Get the command list to set the values on the attribute.
    command_list = []
    src_attr.__apimplug__().getSetAttrCmds(command_list)

    # The command list operates on the selected node, so select the destination node.  
    old_selection = pm.ls(sl=True)
    pm.select(dst_attr.node())

    # Run the commands.
    for cmd in command_list:
        pm.mel.eval(cmd)
    pm.select(old_selection)

#class WrappedBlendShapes(object):
#    """
#    Work with wrapped blend shapes.  A wrapped blend shape is one that receives retargetted
#    blend shapes from a source.
#    """
#    @classmethod
#    def get_blend_shape_wrap_target(cls, follower_blend_shape):
#        """
#        Return a list of all blendShape nodes that receive retargets from blend_shape.
#        """
#        assert isinstance(follower_blend_shape, pm.nodetypes.BlendShape), 'Expected a blendShape, got: %s' % follower_blend_shape.type()
#        if not pm.attributeQuery('wrappingBlendShape', node=follower_blend_shape.nodeName(), exists=True):
#            return None
#
#        dst_attr = follower_blend_shape.attr('wrappingBlendShape')
#
#        # There can only be zero or one incoming connections.
#        connections = dst_attr.connections(s=True, d=False)
#        assert len(connections) <= 1
#        if not connections:
#            return None
#        return connections[0]
#
#    @classmethod
#    def find_following_blend_shapes(cls, blend_shape):
#        """
#        Return a list of all blendShape nodes that receive retargets from blend_shape.
#        """
#        cls._assert_is_blend_shape(blend_shape)
#        
#        # Find all blend shapes that are retargetted from this one.
#        connections = blend_shape.attr('message').listConnections(type='blendShape', p=True, s=False, d=True)
#        connections = [c.node() for c in connections if c.attrName() == 'wrappingBlendShape']
#        return connections
#
#    @classmethod
#    def add_wrap(cls, follower_blend_shape, blend_shape_node_to_follow):
#        cls._assert_is_blend_shape(follower_blend_shape)
#        cls._assert_is_blend_shape(blend_shape_node_to_follow)
#        
#        # An array of message attributes would be more useful, but there's no way to create that with addAttr.
#        if not pm.attributeQuery('wrappingBlendShape', node=follower_blend_shape.nodeName(), exists=True):
#            pm.addAttr(follower_blend_shape, ln='wrappingBlendShape', at='message')
#
#        src_attr = blend_shape_node_to_follow.attr('message')
#        dst_attr = follower_blend_shape.attr('wrappingBlendShape')
#        if not src_attr.isConnectedTo(dst_attr):
#            src_attr.connect(dst_attr)
#
#    @classmethod
#    def remove_wrap(cls, follower_blend_shape):
#        cls._assert_is_blend_shape(follower_blend_shape)
#
#        # Just delete the wrappingBlendShape attribute.
#        if not pm.attributeQuery('wrappingBlendShape', node=follower_blend_shape.nodeName(), exists=True):
#            return
#
#        pm.deleteAttr(follower_blend_shape.attr('wrappingBlendShape'))
#
#    @classmethod
#    def find_dst_blend_shape_node(cls, src_blend_shape_node, dst_mesh):
#        """
#        Given a source blend shape and a target mesh, find the blend shape on the target
#        mesh which receives retargetting from the source blend shape.
#        
#        The SourceBlendShape attribute is used to track this.  It's very inconvenient to
#        select multiple blend shape nodes and specific attributes on them, so this allows
#        only having to select the meshes.
#        """
#        cls._assert_is_blend_shape(src_blend_shape_node)
#
#        connections = cls.find_following_blend_shapes(src_blend_shape_node)
#
#        # One of the blend shapes should be in the history of dst_mesh.
#        # XXX: look at futures of the base mesh
#        dst_mesh_history = dst_mesh.listHistory()
#        for conn in connections:
#            if conn.node() in dst_mesh_history:
#                return conn.node()
#        return None
#
#    @classmethod
#    def _assert_is_blend_shape(cls, node):
#        assert isinstance(node, pm.nodetypes.BlendShape), 'Expected a blendShape, got: %s' % node.type()

class UI(maya_helpers.OptionsBox):
    title = 'Retarget Blend Shapes'

    def get_src_blend_shape_name(self):
        return pm.optionMenuGrp('sourceBlendShapeList', q=True, v=True)
    
    def get_dst_blend_shape_name(self):
        return pm.optionMenuGrp('dstBlendShapeList', q=True, v=True)

    def option_box_load(self):
        """
        Load saved settings from optionVars to the UI.
        """
        connect_weights_to_source = self.optvars['zBlendShapeRetargettingConnectWeightsToSource'] == 1
        pm.checkBoxGrp('connectWeightsToSource', edit=True, value1=connect_weights_to_source)

        # optionMenuGrp will throw RuntimeError if the value doesn't exist, eg. the saved blendShape
        # node doesn't exist in the scene.
#        def set_option_from_blend_shape_list(blend_shape_list, option_var):
#            menu_items = pm.optionMenuGrp(blend_shape_list, q=True, itemListLong=True)
#            all_menu_items = [pm.menuItem(item, q=True, label=True) for item in menu_items]
#            src_blend_shape = pm.optionVar(q=option_var)
#            if src_blend_shape in all_menu_items:
#                pm.optionMenuGrp(blend_shape_list, e=True, v=src_blend_shape)
#        set_option_from_blend_shape_list('sourceBlendShapeList', 'zBlendShapeRetargettingSourceBlendShape')
#        set_option_from_blend_shape_list('dstBlendShapeList', 'zBlendShapeRetargettingTargetBlendShape')

    def option_box_save(self):
        self.optvars['zBlendShapeRetargettingConnectWeightsToSource'] = pm.checkBoxGrp('connectWeightsToSource', q=True, value1=False)

    def option_box_apply(self):
        # Get the selected blendShapes.
        src_blend_shape = pm.optionMenuGrp('sourceBlendShapeList', q=True, v=True)
        dst_blend_shape = pm.optionMenuGrp('dstBlendShapeList', q=True, v=True)
        src_blend_shape = pm.ls(src_blend_shape)[0]
        dst_blend_shape = pm.ls(dst_blend_shape)[0]

        if not src_blend_shape:
            pm.warning('No source blend shape is selected')
            return

        if not dst_blend_shape:
            pm.warning('No target blend shape is selected')
            return

        if src_blend_shape == dst_blend_shape:
            pm.warning('The source and destination blend shapes are the same')
            return

        # These were selected from the UI, so unless the scene changed while the dialog was
        # open these should always be blendShape nodes.
        assert isinstance(src_blend_shape, pm.nodetypes.BlendShape), 'Node %s isn\'t a blend shape' % src_blend_shape.nodeName()
        assert isinstance(dst_blend_shape, pm.nodetypes.BlendShape), 'Node %s isn\'t a blend shape' % dst_blend_shape.nodeName()

        # Get the selected blend shape targets to retarget.
        blend_shape_targets = self.get_selected_src_blend_shape_targets()
        blend_shape_indices = [target.index() for target in blend_shape_targets]
        if not blend_shape_indices:
            pm.warning('No blend shape targets are selected')
            return

        src_blend_shape_targets = pm.ls(pm.blendShape(src_blend_shape, q=True, g=True))
        dst_blend_shape_targets = pm.ls(pm.blendShape(dst_blend_shape, q=True, g=True))

        # Make sure that both blend shapes have just one target.
        assert len(src_blend_shape_targets) == 1, 'Blend shape %s must have one target, has %i: %s' % (
                src_blend_shape.nodeName(),
                len(src_blend_shape_targets), ', '.join(src_blend_shape_targets))
        assert len(dst_blend_shape_targets) == 1, 'Blend shape %s must have one target, has %i: %s' % (
                dst_blend_shape.nodeName(),
                len(dst_blend_shape_targets), ', '.join(dst_blend_shape_targets))

        # Find the transforms for the source and destination node.
        src_node = src_blend_shape_targets[0].getTransform()
        dst_node = dst_blend_shape_targets[0].getTransform()

        # Check the selected nodes.
        assert isinstance(src_node, pm.nodetypes.Transform), 'The source node %s isn\'t a transform' % src_node.nodeName()
        assert isinstance(dst_node, pm.nodetypes.Transform), 'The destination node %s isn\'t a transform' % dst_node.nodeName()
        assert src_node.getShape() is not None, 'The source node %s isn\'t a mesh' % dst_node.nodeName()
        assert dst_node.getShape() is not None, 'The destination node %s isn\'t a mesh' % dst_node.nodeName()

    #    # Find all blendShapes that are following this one.
    #    following_blend_shapes = WrappedBlendShapes.find_following_blend_shapes(src_blend_shape)
    #
    #    # Find a blend shape node on dst_node that's in following_blend_shapes.  We can either
    #    # look in the history of the output mesh, or in the future of the base mesh, and both can
    #    # have wrong matches.
    #    for node in dst_node.getShapes()[-1].listFuture():
    #        if node in following_blend_shapes:
    #            dst_blend_shape = node
    #            break
    #    else:
    #        raise RuntimeError('Couldn\'t find a blend shape node on %s which is following %s' % (dst_node.name(), src_blend_shape.name()))

        connect_weights = pm.checkBoxGrp('connectWeightsToSource', q=True, value1=False)
        redst_blend_shapes(src_node, dst_node, src_blend_shape, dst_blend_shape, blend_shape_indices, connect_weights=connect_weights)

    def options_box_setup(self):
        self.optvars.add('zBlendShapeRetargettingConnectWeightsToSource', 'int', 0)
        
        parent = pm.columnLayout(adjustableColumn=True)

        def add_blend_shape_selector(name, label, refresh_on_change):
            pm.optionMenuGrp(name, label=label)

            # Create a list of blendShapes.
            bnArray = pm.ls(type='blendShape')
            for entry in bnArray:
                pm.menuItem(label=entry)
            if not bnArray:
                pm.menuItem(label='No Blend Shape Selected')

            # When the source selection is changed, update the source blend shape list.
            def changed(value):
                self.refresh_src_blend_shape_list()
            if refresh_on_change:
                pm.optionMenuGrp(name, edit=True, changeCommand=changed)

        add_blend_shape_selector('sourceBlendShapeList', 'Source blendShape', True)
        add_blend_shape_selector('dstBlendShapeList', 'Target blendShape', False)

        pm.separator()

        pm.textScrollList('blendShapeTargetList', numberOfRows=10, allowMultiSelection=True)
#                        showIndexedItem=4 )
        pm.separator()
       
        pm.checkBoxGrp('connectWeightsToSource', numberOfCheckBoxes=1, value1=False, label='Connect weights to source')

        self.refresh_src_blend_shape_list()

    def refresh_src_blend_shape_list(self):
        pm.textScrollList('blendShapeTargetList', edit=True, removeAll=True)

        src_blend_shape = self.get_src_blend_shape_name()
        if src_blend_shape is None:
            return
        if src_blend_shape == 'No Blend Shape Selected':
            return

        # The blend shape array is sparse, so keep a mapping from list indices to blend
        # shape weight indices.  Note that for some reason, these are 1-based.
        self.src_blend_shape_map = {}

        # Add the blend shape targets in the source blend shape to the list.
        src_blend_shape = pm.ls(src_blend_shape)[0]

        weight_idx_list = src_blend_shape.weightIndexList()
        src_weights = src_blend_shape.attr('weight')
        for weight_idx in weight_idx_list:
            weight = src_weights.elementByLogicalIndex(weight_idx)
            target_name = pm.aliasAttr(weight, q=True)

            pm.textScrollList('blendShapeTargetList', edit=True, append=target_name)
            idx = pm.textScrollList('blendShapeTargetList', q=True, numberOfItems=True)
            self.src_blend_shape_map[idx] = weight

    def get_selected_src_blend_shape_targets(self):
        selection = pm.textScrollList('blendShapeTargetList', q=True, selectIndexedItem=True)
        return [self.src_blend_shape_map[idx] for idx in selection]

