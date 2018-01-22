import math, re
import pymel.core as pm
import maya.cmds as cmds
import maya.OpenMaya as OpenMaya
import maya.OpenMayaAnim as OpenMayaAnim
from zMayaTools.menus import Menu
from zMayaTools import maya_logging, maya_helpers

log = maya_logging.get_log()

def scale(x, l1, h1, l2, h2):
    return (x - l1) * (h2 - l2) / (h1 - l1) + l2
def _to_vtx_list(p):
    return [(x, y, z) for x, y, z in zip(p[0::3], p[1::3], p[2::3])]

def split_blend_shape(base_mesh, target_mesh, right_side=True, fade_distance=2, axis=0, axis_origin=0):
    # Read the positions in world space.  Although the shapes should be in the same position,
    # we want world space units so the distance factor makes sense.
    #
    # We do this with cmds instead of pm, since it's faster for dealing with lots of vertex
    # data.
    target_pos = _to_vtx_list(cmds.xform('%s.vtx[*]' % target_mesh, q=True, t=True, ws=True))
    base_pos = _to_vtx_list(cmds.xform('%s.vtx[*]' % base_mesh, q=True, t=True, ws=True))
    if len(target_pos) != len(base_pos):
        OpenMaya.MGlobal.displayError('Target has %i vertices, but base has %i vertices.' % (len(target_pos) != len(base_pos)))
        return

    result_pos = []
    new_target_pos = []
    for idx in xrange(len(target_pos)):
        dist = target_pos[idx][axis]
        dist -= axis_origin

        if fade_distance == 0:
            p = 0 if dist < 0 else 1
        else:
            p = scale(dist, -fade_distance/2.0, fade_distance/2.0, 0, 1.0)

        # If we're fading in the left side instead of the right, flip the value.
        if not right_side:
            p = 1-p

        p = min(max(p, 0), 1)

        # Clean up the percentage.  It's easy to end up with lots of values like 0.000001, and clamping
        # them to zero or one can give a smaller file.
        if p < 0.001: p = 0
        if p > .999: p = 1
        delta = [target_pos[idx][i] - base_pos[idx][i] for i in range(3)]
        new_target_pos.append([base_pos[idx][i] + delta[i]*p for i in range(3)])

    def distance_squared(a, b):
        p0 = math.pow(a[0]-b[0], 2)
        p1 = math.pow(a[1]-b[1], 2)
        p2 = math.pow(a[2]-b[2], 2)
        return math.pow(p0 + p1 + p2, 1)

    for idx in xrange(len(new_target_pos)):
        old = target_pos[idx]
        new = new_target_pos[idx]
        if distance_squared(old, new) < 0.0001:
            continue
        cmds.xform('%s.vtx[%i]' % (target_mesh, idx), t=new_target_pos[idx], ws=True)

def get_connected_input_geometry(blend_shape):
	"""
	Return an array of blend_shape's input plugs that have an input connection.
	
	pm.listConnections should do this, but it has bugs when the input array is sparse.
	"""
	results = []
	blend_shape_plug = _get_plug_from_node('%s.input' % blend_shape)
	num_input_elements = blend_shape_plug.evaluateNumElements()
	for idx in xrange(num_input_elements):
            input = blend_shape_plug.elementByPhysicalIndex(idx)
            input_geometry_attr = OpenMaya.MFnDependencyNode(input.node()).attribute('inputGeometry')
            input_geometry_plug = input.child(input_geometry_attr)
            conns = OpenMaya.MPlugArray()
            input_geometry_plug.connectedTo(conns, True, False);
            if conns.length():
                results.append(input_geometry_plug.info())
	return results

def _find_output_mesh(plug):
    # pm.listHistory will traverse the graph to find an output mesh, but it only works
    # on nodes, not plugs.  Go from the plug to the next node.  If there's more than one
    # output connection, we won't know which one to follow.
    connections = pm.listConnections(plug, s=False, d=True) or []
    if len(connections) != 1:
        raise RuntimeError('Expected one connection out of %s, got: %s' % (plug, connections))

    for node in pm.listHistory(connections[0], f=True):
        if node.nodeType() != 'mesh':
            continue
        return node
    else:
        OpenMaya.MGlobal.displayError('Couldn\'t find a mesh in the future of %s.' % deformer)

def _get_plug_from_node(node):
    selection_list = OpenMaya.MSelectionList()
    selection_list.add(node)
    plug = OpenMaya.MPlug()
    selection_list.getPlug(0, plug)
    return plug

def _copy_mesh_from_plug(path):
    plug = _get_plug_from_node(path)
    mesh = OpenMaya.MFnMesh().copy(plug.asMObject())
    return pm.ls(OpenMaya.MFnTransform(mesh).partialPathName())[0]

def get_weight_from_alias(blend_shape, alias):
    """
    Given a blend shape node and an aliased weight attribute, return the index in .weight to the
    alias.
    """
    # aliasAttr lets us get the alias from an attribute, but it doesn't let us get the attribute
    # from the alias.
    existing_indexes = blend_shape.attr('weight').get(mi=True) or []
    for idx in existing_indexes:
        aliasName = pm.aliasAttr(blend_shape.attr('weight').elementByLogicalIndex(idx), q=True)
        if aliasName == alias:
            return idx
    raise Exception('Couldn\'t find the weight index for blend shape target %s.%s' % (blend_shape, alias))

def split_all_blend_shape_targets(blend_shape, *args, **kwargs):
    blend_targets = pm.listAttr(blend_shape.attr('w'), m=True) or []
    for blend_target in blend_targets:
        split_blend_shape_from_deformer(blend_shape, blend_target, *args, **kwargs)

def substitute_name(pattern, name, left_side):
    """
    Replace substitutions in a name pattern.

    <name> will be replaced with the value of name.
    Patterns containing a pipe, eg.  <ABCD|EFGH>, will be replaced with "ABCD"
    if left_side is true or "EFGH" if left_side is false.
    """
    def sub(s):
        text = s.group(1)
        if text == 'name':
            return name

        if '|' in text:
            parts = text.split('|', 2)
            if left_side or len(parts) == 1:
                return parts[0]
            else:
                return parts[1]

        return s.group(0)
    return re.sub(r'<([^>]*)>', sub, pattern)

def split_blend_shape_from_deformer(blend_shape, blendTarget,
        outputBlendShapeLeft=None, outputBlendShapeRight=None,
        naming_pattern='<Name>',
        split_args={}):
    """
    outputBlendShapeLeft, outputBlendShapeRight: If not None, the blend_shape deformers
    to put the resulting blend shapes.  If None, the blend shapes are added to the same
    deformer as their source.

    If we're adding the new shapes to separate deformers, we'll always add it at the same
    target index as the source.  This makes it easier to keep track of which target is
    which.  If there's already a blend shape on that index, we'll try to overwrite it.
    Currently this will fail if there's a mesh input for that target, but we normally
    delete the target meshes to use a delta target instead.
    """
    # XXX: This still doesn't undo correctly.  I'm not sure why.
    pm.undoInfo(openChunk=True)

    try:
        if outputBlendShapeLeft is None:
            # Get the next free blend shape target indexes, for the new blend shapes we'll create.
            existing_indexes = pm.getAttr(blend_shape.attr('weight'), mi=True) or [-1]
            output_blend_shape_indexes = {
                'L': max(existing_indexes) + 1,
                'R': max(existing_indexes) + 2,
            }
        else:
            # If we're adding the blend shapes to separate blendShape deformers rather than the
            # same deformer as the source, we'll always use the same index as the source, so that
            # srcBlendShape.w[1] for the full blend shape corresponds to leftBlendShape.w[1] for the
            # left side blend shape.
            weightIndex = get_weight_from_alias(blend_shape, blendTarget)
            output_blend_shape_indexes = {
                'L': weightIndex,
                'R': weightIndex,
            }

        # Save all weights.
        original_weights = {attr.index(): attr.get() for attr in blend_shape.attr('weight')}

        # Disconnect all incoming connections into the weights, so we can manipulate them.  We'll
        # reconnect them when we're done.
        existing_connections = pm.listConnections(blend_shape.attr('weight'), s=True, d=False, p=True, c=True) or []
        for dst, src in existing_connections:
            src.disconnect(dst)

        try:
            # Reset all weights to 0.
            for idx in original_weights.keys():
                try:
                    # Don't try to set weights that are already 0, so we don't print warnings for connected blend
                    # shape weights that we don't actually need to change.
                    if blend_shape.attr('weight').elementByLogicalIndex(idx).get() == 0:
                        continue
                            
                    blend_shape.attr('weight').elementByLogicalIndex(idx).set(0)
                except RuntimeError as e:
                    log.error('Couldn\'t disable blend shape target: %s' % e)

            # Turn on the blend shape that we're splitting.
            blend_shape.attr(blendTarget).set(1)
       
            # Get a list of the inputGeometry plugs on the blend shape that are connected.
            connected_input_geometry = get_connected_input_geometry(blend_shape)

            # Split each mesh.
            for input_geom in connected_input_geometry:
                # Figure out the outputGeometry for this inputGeometry.  Maya knows this
                # via passThroughToMany, but I don't know how to access that information here.
                # Search and replace input[*].inputGeometry -> outputGeometry[*].
                output_geom = input_geom.replace('.inputGeometry', '')
                output_geom = output_geom.replace('.input', '.outputGeometry')

                # Make a separate copy of the blended mesh for the left and right sides, and a copy of the input
                # into the blend shape.  We do this directly from the blend shape's plugs, so we're not affected
                # by other deformers.
                new_mesh_base = _copy_mesh_from_plug(output_geom)
                for side in ('L', 'R'):
                    new_mesh = _copy_mesh_from_plug(input_geom)
            
                    # Rename the blended nodes, since the name of this node will become the name of the
                    # blend shape target.
                    new_mesh_name = substitute_name(naming_pattern, blendTarget, side == 'L')
                    new_mesh.rename(new_mesh_name)
                    
                    # Fade the left and right shapes to their respective sides.
                    split_blend_shape(new_mesh_base, new_mesh, right_side=side == 'R', **split_args)
            
                    # Find the mesh that output_geom is connected to.
                    output_mesh = _find_output_mesh(output_geom)

                    # Create the two blend shapes (or add them to the existing blend shape if there
                    # are multiple meshes attached to the deformer).
                    if outputBlendShapeLeft:
                        outputShape = outputBlendShapeLeft if side == 'L' else outputBlendShapeRight
                    else:
                        outputShape = blend_shape
                    pm.blendShape(outputShape, edit=True, t=(output_mesh, output_blend_shape_indexes[side], new_mesh, 1))

                    # Delete the mesh.  It'll be stored in the blendShape.
                    pm.delete(new_mesh)

                pm.delete(new_mesh_base)
    
        finally:
            # Reset blend shape weights that we disabled.
            for idx, weight in original_weights.items():
                try:
                    attr = blend_shape.attr('weight').elementByLogicalIndex(idx)
                    if attr.get() == weight:
                            continue
                            
                    attr.set(weight)
                except RuntimeError as e:
                        log.error('Couldn\'t disable blend shape target: %s' % e)

            # Reconnect any incoming connections to the weights that we disconnected above.
            for dst, src in existing_connections:
                src.connect(dst)
    finally:
        pm.undoInfo(closeChunk=True)

class UI(maya_helpers.OptionsBox):
    title = 'Split Blend Shape'

    def options_box_setup(self):
        self.optvars.add('zSplitBlendShapesBlendDistance', 'float', 2)
        self.optvars.add('zSplitBlendShapesPlane', 'int', 2)
        self.optvars.add('zSplitBlendShapesPlaneOrigin', 'float', 0)
        self.optvars.add('zSplitBlendShapesNamingPattern', 'string', '<name>_<L|R>')
        
        parent = pm.columnLayout(adjustableColumn=1)

        pm.optionMenuGrp('sbsList', label='Blend shape:', cc=self.fill_blend_target)
        self.fill_blend_shapes('sbsList|OptionMenu', False)

        pm.optionMenuGrp('sbsLeftOutput', label='Left output:')
        self.fill_blend_shapes('sbsLeftOutput|OptionMenu', True)

        pm.optionMenuGrp('sbsRightOutput', label='Right output:')
        self.fill_blend_shapes('sbsRightOutput|OptionMenu', True)

        # If something is selected, try to find a blend shape to select by default.
        selection = pm.ls(sl=True)
        if selection:
            history = pm.listHistory(selection)
            blend_shapes = pm.ls(history, type='blendShape')
            if blend_shapes:
                default_blend_shape = blend_shapes[0]
                self.select_blend_shape(default_blend_shape)

        pm.optionMenuGrp('sbsTargetList', label='Blend target:')
        self.fill_blend_target()

        pm.floatSliderGrp('sbsBlendDistance', label='Blend distance', field=True, min=0, max=10, fieldMinValue=0, fieldMaxValue=1000)
        pm.radioButtonGrp('sbsPlane', label='Plane:', numberOfRadioButtons=3, labelArray3=('XY', 'YZ', 'XZ'))
        pm.floatSliderGrp('sbsPlaneOrigin', label='Plane origin', v=0, min=0, max=1000)
        pm.textFieldGrp('sbsNamingPattern', label='Naming pattern')

    def fill_blend_target(self, unused=True):
        # Clear the existing target list.
        for item in pm.optionMenu('sbsTargetList|OptionMenu', q=True, itemListLong=True):
            pm.deleteUI(item)

        # Prevent a warning from being printed if there aren't any blendShapes.
        if pm.optionMenuGrp('sbsList', q=True, ni=True) == 0:
            return

        # Get the names of the targets in the selected blend shape.
        value = pm.optionMenuGrp('sbsList', q=True, v=True)

        if not value:
            return
        nodes = pm.ls(value)
        if not nodes:
            return
        node = nodes[0]

        pm.menuItem(label='All', parent='sbsTargetList|OptionMenu')

        for item in node.attr('w'):
            target_name = pm.aliasAttr(item, q=True)
            pm.menuItem(label=target_name, parent='sbsTargetList|OptionMenu')

    def select_blend_shape(self, blend_shape):
        menu_items = pm.optionMenu('sbsList|OptionMenu', q=True, itemListLong=True)
        for idx, menu_item in enumerate(menu_items):
            item = pm.menuItem(menu_item, q=True, label=True)

            nodes = pm.ls(item)
            if not nodes:
                continue
            node = nodes[0]

            if node != blend_shape:
                continue;

            pm.optionMenuGrp('sbsList', edit=True, select=idx + 1)

    def fill_blend_shapes(self, target, includeSame):
        for item in pm.optionMenu(target, q=True, itemListLong=True):
            pm.deleteUI(item)

        if includeSame:
            pm.menuItem(parent=target, label='Same deformer as source')

        for item in pm.ls(type='blendShape'):
            pm.menuItem(parent=target, label=item)

    def option_box_apply(self):
        kwargs = { }

        blend_shape = pm.optionMenuGrp('sbsList', q=True, v=True)
        blend_shape = pm.ls(blend_shape)[0]
        leftOutput = None
        rightOutput = None
        if pm.optionMenuGrp('sbsLeftOutput', q=True, sl=True) != 1: # "Same deformer as source"
            leftOutput = pm.optionMenuGrp('sbsLeftOutput', q=True, v=True)
            leftOutput = pm.ls(leftOutput)[0]
        if pm.optionMenuGrp('sbsRightOutput', q=True, sl=True) != 1: # "Same deformer as source"
            rightOutput = pm.optionMenuGrp('sbsRightOutput', q=True, v=True)
            rightOutput = pm.ls(rightOutput)[0]
        blendShapeTarget = ''
        if pm.optionMenuGrp('sbsTargetList', q=True, sl=True) != 1: # "All"
            blendShapeTarget = pm.optionMenuGrp('sbsTargetList', q=True, v=True)
        distance = pm.floatSliderGrp('sbsBlendDistance', q=True, v=True)
        origin = pm.floatSliderGrp('sbsPlaneOrigin', q=True, v=True)
        plane = pm.radioButtonGrp('sbsPlane', q=True, sl=True)
        kwargs['naming_pattern'] = pm.textFieldGrp('sbsNamingPattern', q=True, text=True)

        plane_to_axis = {
            1: 2,
            2: 0,
            0: 1,
        }
        axis = plane_to_axis[plane]

        if blendShapeTarget != "":
            func = split_blend_shape_from_deformer
            kwargs['blendTarget'] = blendShapeTarget
        else:
            func = split_all_blend_shape_targets

        kwargs['blend_shape'] = blend_shape
        if leftOutput:
            kwargs['outputBlendShapeLeft'] = leftOutput
        if rightOutput:
            kwargs['outputBlendShapeRight'] = rightOutput
        split_args = {}
        kwargs['split_args'] = split_args
        split_args['fade_distance'] = distance
        split_args['axis'] = axis
        split_args['axis_origin'] = origin
        func(**kwargs)

    def option_box_load(self):
        pm.floatSliderGrp('sbsBlendDistance', edit=True, v=self.optvars['zSplitBlendShapesBlendDistance'])
        pm.radioButtonGrp('sbsPlane', edit=True, select=self.optvars['zSplitBlendShapesPlane'])
        pm.floatSliderGrp('sbsPlaneOrigin', edit=True, v=self.optvars['zSplitBlendShapesPlaneOrigin'])
        pm.textFieldGrp('sbsNamingPattern', edit=True, text=self.optvars['zSplitBlendShapesNamingPattern'])

    def option_box_save(self):
        self.optvars['zSplitBlendShapesBlendDistance'] = pm.floatSliderGrp('sbsBlendDistance', q=True, v=True)
        self.optvars['zSplitBlendShapesPlane'] = pm.radioButtonGrp('sbsPlane', q=True, select=True)
        self.optvars['zSplitBlendShapesPlaneOrigin'] = pm.floatSliderGrp('sbsPlaneOrigin', q=True, v=True)
        self.optvars['zSplitBlendShapesNamingPattern'] = pm.textFieldGrp('sbsNamingPattern', q=True, text=True)

def run():
    ui = UI()
    ui.run()

