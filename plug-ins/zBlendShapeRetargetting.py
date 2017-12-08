import math, inspect, os, sys, time
import pymel.core as pm
import maya.cmds as cmds
from zMayaTools.menus import Menu

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

        return redst_blend_shapes_inner(src_node, dst_node, src_blend_shape_node, dst_blend_shape_node, blend_shape_indices, connect_weights)
    finally:
        pm.waitCursor(state=False)

        # Delete the temporary namespace.
        pm.namespace(setNamespace=old_namespace)
        pm.namespace(rm=':temp', deleteNamespaceContent=True)

        pm.select(old_selection)

def redst_blend_shapes_inner(src_node, dst_node, src_blend_shape_node, dst_blend_shape_node, blend_shape_indices, connect_weights):
    # Duplicate the base meshes.
    src_node_copy = duplicate_base_mesh(src_node)
    dst_node_copy = duplicate_base_mesh(dst_node)

    # Add a blend shape deformer to the duplicated source mesh, and copy blend shape
    # targets to it from the source.
    duplicate_src_blend_shape = pm.blendShape(src_node_copy)[0]
    copy_blend_shapes(src_blend_shape_node, duplicate_src_blend_shape)

    # Wrap dst_node_copy to src_node_copy, so the destination mesh follows blend shapes on the source mesh.
    wrap_deformer(src_node_copy, dst_node_copy, auto_weight_threshold=True, falloff_mode=0)

    # Find all blend shape names.  We require that blend shapes have a name, and always give
    # blend shapes the same name as their source.
    dst_blend_shape_name_to_index = {}
    for idx in dst_blend_shape_node.weightIndexList():
        src_weight = dst_blend_shape_node.attr('w').elementByLogicalIndex(idx)
        target_name = pm.aliasAttr(src_weight, q=True)
        
        if target_name is None:
            print 'Warning: destination blend shape has an unused blend shape %i' % idx
            continue
        
        dst_blend_shape_name_to_index[target_name] = idx

    def get_unused_blend_shape_index():
        # Return an index that isn't in use in dst_blend_shape_name_to_index.
        index_list = sorted(dst_blend_shape_name_to_index.values())
        for idx in xrange(0, len(index_list)+1):
            if idx not in index_list:
                return idx
        raise RuntimeError('Not reachable')

    # Do the actual retargetting.
    for idx in blend_shape_indices:
        # Make sure that we aren't connected backwards, or this would create a cycle.
        src_weight = src_blend_shape_node.attr('weight').elementByLogicalIndex(idx)

        # Each index is a weight attribute on the source blend shape deformer.  Get the name of the blend shape.
        target_name = pm.aliasAttr(src_weight, q=True)
        if target_name is None:
            print 'Error: blend shape index %i has no name' % idx
            continue

        # Find the blend shape in the target with this name.  If it already exists, we'll just update
        # it.  Otherwise, we'll pick a new index and create a new one.
        new_idx = dst_blend_shape_name_to_index.get(target_name)
        if new_idx is None:
            # There's no existing blend shape by this name.  Find an unused one, and record that we've
            # used it.
            new_idx = get_unused_blend_shape_index()
            dst_blend_shape_name_to_index[target_name] = new_idx

        dst_weight = dst_blend_shape_node.attr('weight').elementByLogicalIndex(new_idx)
        if dst_weight.isConnectedTo(src_weight):
            print 'Warning: the destination target %s is a source for the source %s.  Are the blend shapes selected backwards?' % (
                    dst_weight, src_weight)
            continue

        # Enable the blend shape target on the source object.  This will deform dst_node_copy through
        # the wrap deformer.
        weight = duplicate_src_blend_shape.attr('w').elementByLogicalIndex(idx)
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

        # Rename the blend shape target to match the source.
        old_alias = pm.aliasAttr(dst_weight, q=True)
        pm.aliasAttr(dst_blend_shape_node.attr(old_alias), rm=True)
        pm.aliasAttr(target_name, dst_weight)

        # Disable the target.
        weight.set(0)

        # We don't need the copied target.  Once we delete this, the blend shape will be baked into
        # the deformer.
        pm.delete(new_blend_shape_target)

        # Connect the source blend shape's weight to the target.
        if connect_weights:
            src_weight.connect(dst_weight)

def _create_wrap(control_object, target,
        threshold=0,
        max_distance=0,
        influence_type=2, # 1 for point, 2 for face
        exclusive=False,
        auto_weight_threshold=False,
        render_influences=True,
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
        'render_influences': 1 if render_influences else 0,
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
    if not load_plugin('cvwrap.mll', required=False):
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
        render_influences=False,
        falloff_mode=0): # 0 for volume, 1 for surface
    # If any nodes are meshes, move up to the transform.
    selection = target.getParent() if target.nodeType() == 'mesh' else target

    # Work around a bit of Maya nastiness.  Creating a wrap deformer doesn't hide the influence
    # mesh normally, it turns a bunch of renderer flags off instead, to make it look like the
    # mesh hasn't been changed and then screw you up later when you render.  We have to save and
    # restore a bunch of properties manually to fix this.
    attributes_hijacked_by_wrap = ('castsShadows', 'receiveShadows', 'motionBlur',
            'primaryVisibility', 'visibleInReflections', 'visibleInRefractions')
    saved_attrs = {attr: control_mesh.attr(attr).get() for attr in attributes_hijacked_by_wrap}

    control_transform = control_mesh.getParent() if control_mesh.nodeType() == 'mesh' else control_mesh

    deformer_node = None
    if use_cvwrap_if_available:
        deformer_node = _create_cvwrap(control_transform, selection)
        if deformer_node is None:
            log.warning('The cvwrap plugin isn\'t available.')

    if deformer_node is None:
        deformer_node = _create_wrap(control_transform, selection, threshold, max_distance, influence_type,
            exclusive, auto_weight_threshold, render_influences, falloff_mode)

    # Restore the attributes that wrap screwed up.
    for attr, value in saved_attrs.items():
        control_mesh.attr(attr).set(value)

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

def copy_blend_shapes(src, dst):
    """
    Copy all blend shape targets from src to dst.
    """
    # Set the blend shape weights on the target to 0, so they show up in the CB.  Don't
    # copy the weights from the source.
    src_weights = src.attr('weight')
    dst_weights = dst.attr('weight')
    for weight_idx in src_weights.get(mi=True):
        dst_weights.elementByLogicalIndex(weight_idx).set(0)

    # Copy the targets.
    copy_attr(src.attr('inputTarget'), dst.attr('inputTarget'))

#    src_input_targets = src.attr('inputTarget')
#    dst_input_targets = dst.attr('inputTarget')
#
#    for it_idx in src_input_targets.get(mi=True):
#        src_input_target = src_input_targets.elementByLogicalIndex(it_idx)
#        dst_input_target = dst_input_targets.elementByLogicalIndex(it_idx)
#        continue
#
#        src_input_target_groups = src_input_target.attr('inputTargetGroup')
#        dst_input_target_groups = dst_input_target.attr('inputTargetGroup')
#        for itg_idx in src_input_target_groups.get(mi=True):
#            src_input_target_group = src_input_target_groups.elementByLogicalIndex(itg_idx)
#            dst_input_target_group = dst_input_target_groups.elementByLogicalIndex(itg_idx)
#
#            src_input_target_items = src_input_target_group.attr('inputTargetItem')
#            dst_input_target_items = dst_input_target_group.attr('inputTargetItem')
#            for iti_idx in src_input_target_items.get(mi=True):
#                src_input_target_item = src_input_target_items.elementByLogicalIndex(iti_idx)
#                dst_input_target_item = dst_input_target_items.elementByLogicalIndex(iti_idx)
#
#                for attr_name in ('inputGeomTarget', 'inputRelativePointsTarget',
#                    'inputRelativeComponentsTarget', 'inputPointsTarget', 'inputComponentsTarget'):
#                    src_attr = src_input_target_item.attr(attr_name)
#                    dst_attr = dst_input_target_item.attr(attr_name)
#
#                    attr_type = src_attr.type()
#
#                    source = pm.listConnections(src_attr, s=True, d=False)
#                    if source:
#                        # Connect input connections.
#                        assert len(source) == 1
#                        source[0].connect(dst_attr)
#                    else:
#                        copy_attr(src_attr, dst)

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

def xrun():
    # Select the target blend shape, then the source blend shape, then the blend shape targets
    # to retarget in the channel box.
    #
    # (Selecting multiple blendShape nodes is a pain.  Graph the meshes in the node editor and
    # select them there.)
    selection = pm.ls(sl=True, type='blendShape')
    if len(selection) < 2:
        print 'Select the target mesh, then the source mesh, then a blend shape node in the channel box'
        return

    dst_blend_shape = selection[0]
    src_blend_shape = selection[1]
    assert isinstance(src_blend_shape, pm.nodetypes.BlendShape), 'Node %s isn\'t a blend shape' % src_blend_shape.nodeName()
    assert isinstance(dst_blend_shape, pm.nodetypes.BlendShape), 'Node %s isn\'t a blend shape' % dst_blend_shape.nodeName()

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

    # Get the blend shape targets to retarget from the channel box.
    channel_box = pm.MelGlobals.get('gChannelBoxName')
    #selected_attrs = pm.channelBox(channel_box, q=True, selectedHistoryAttributes=True) or []
    selected_attrs = pm.channelBox(channel_box, q=True, selectedMainAttributes=True) or []
    blend_shape_targets = [src_blend_shape.attr(attr) for attr in selected_attrs]

    # Convert the selected blend shape targets to their blend shape indices.
    blend_shape_indices = []
    for target in blend_shape_targets:
        # Each target should be a weight attribute on the source blend shape deformer.
        if not target.isElement():
            continue
        if target.array().plugAttr() != 'w':
            continue
        blend_shape_indices.append(target.index())

    if not blend_shape_indices:
        print 'No blend shape targets are selected'
        return

    redst_blend_shapes(src_node, dst_node, src_blend_shape, dst_blend_shape, blend_shape_indices, connect_weights=Trues
)

class UI(object):
    def get_src_blend_shape_name(self):
        return pm.optionMenuGrp('sourceBlendShapeList', q=True, v=True)
    
    def get_dst_blend_shape_name(self):
        return pm.optionMenuGrp('dstBlendShapeList', q=True, v=True)

    def set_optionvars_from_ui(self):
        """
        Store saved settings to optionVars.
        """
        connect_weights_to_source = pm.checkBoxGrp('connectWeightsToSource', q=True, value1=False)
        pm.optionVar(intValue=('zBlendShapeRetargettingConnectWeightsToSource', connect_weights_to_source))

    def load_ui_from_optionvars(self, parent):
        """
        Load saved settings from optionVars to the UI.
        """
        pm.setParent(parent)

        if pm.optionVar(exists='zBlendShapeRetargettingSourceBlendShape'):
            connect_weights_to_source = pm.optionVar(q='zBlendShapeRetargettingConnectWeightsToSource') == 1
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

    def reset_optionvars(self):
        pm.optionVar(remove='zBlendShapeRetargettingConnectWeightsToSource')

    def execute_from_dialog(self):
        self.set_optionvars_from_ui()
        self.execute_from_optionvars()

    def execute_from_optionvars(self):
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

    def run(self):
        option_box = pm.mel.eval('getOptionBox()')

        pm.setParent(option_box)
        pm.mel.eval('setOptionBoxCommandName("blendShape");')
        pm.setUITemplate('DefaultTemplate', pushTemplate=True)

        pm.tabLayout(tabsVisible=False, scrollable=True)
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

        pm.setUITemplate(popTemplate=True)    
        
        def apply(unused):
            self.execute_from_dialog()

        def apply_and_close(unused):
            self.execute_from_dialog()
            pm.mel.eval('hideOptionBox')

        def save(unused):
            self.set_optionvars_from_ui()

        def reset(unused):
            self.reset_optionvars()
            self.load_ui_from_optionvars(parent)

        # We need to set both apply and apply and close explicitly.  Maya breaks apply and close
        # if apply is set to a Python function.
        pm.button(pm.mel.eval('getOptionBoxApplyBtn()'), edit=True, command=apply)
        pm.button(pm.mel.eval('getOptionBoxApplyAndCloseBtn()'), edit=True, command=apply_and_close)

        pm.mel.eval('setOptionBoxTitle "Retarget Blend Shapes"')
        pm.mel.eval('setOptionBoxHelpTag "Retarget Blend Shapes"')
        self.load_ui_from_optionvars(parent)
        
        self.refresh_src_blend_shape_list()

        pm.mel.eval('showOptionBox')

        # To work around a Maya bug, we need to set save and reset directly to the menu,
        # rather than to the buttons, and do it after calling showOptionBox, or they
        # won't work.
        save_menu_item = pm.mel.globals['gOptionBoxEditMenuSaveItem']
        reset_menu_item = pm.mel.globals['gOptionBoxEditMenuResetItem']
        pm.menuItem(save_menu_item, edit=True, command=save)
        pm.menuItem(reset_menu_item, edit=True, command=reset)

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

        src_weights = src_blend_shape.attr('weight')
        for weight in src_weights:
            target_name = pm.aliasAttr(weight, q=True)

            pm.textScrollList('blendShapeTargetList', edit=True, append=target_name)
            idx = pm.textScrollList('blendShapeTargetList', q=True, numberOfItems=True)
            self.src_blend_shape_map[idx] = weight

    def get_selected_src_blend_shape_targets(self):
        selection = pm.textScrollList('blendShapeTargetList', q=True, selectIndexedItem=True)
        return [self.src_blend_shape_map[idx] for idx in selection]

     
def run():
    ui = UI()
    ui.run()

class PluginMenu(Menu):
    def add_menu_items(self):
        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the file menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            for item in pm.menu(menu, q=True, ia=True):
                # Find the "Edit" section.
                if pm.menuItem(item, q=True, divider=True):
                    section = pm.menuItem(item, q=True, label=True)
                if section != 'Edit':
                    continue

                # Find the "Blend Shape" submenu.
                if not pm.menuItem(item, q=True, subMenu=True):
                    continue
                if pm.menuItem(item, q=True, label=True) != 'Blend Shape':
                    continue

                self.add_menu_item('zBlendShapeRetargetting_%s' % menu, label='Retarget Blend Shapes', command=lambda unused: run(), parent=item)

menu = PluginMenu()
def initializePlugin(mobject):
    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

