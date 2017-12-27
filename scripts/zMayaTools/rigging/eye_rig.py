from pymel import core as pm

from zMayaTools import maya_helpers
from zMayaTools import maya_logging
log = maya_logging.get_log()

def average_position(*nodes):
    assert len(nodes) > 0
    positions = [pm.xform(node, q=True, ws=True, t=True) for node in nodes]
    x = sum(v[0] for v in positions)
    y = sum(v[1] for v in positions)
    z = sum(v[2] for v in positions)
    return [x/len(positions), y/len(positions), z/len(positions)];

def create_handle(name):
    pm.loadPlugin('zRigHandle', quiet=True)
    handle = pm.createNode('zRigHandle')
    handle = pm.rename(handle, name + 'Shape')
    parent = pm.listRelatives(handle, p=True, pa=True)
    parent = pm.rename(parent, name)
    return parent.getShape()

def sanity_check_eyes(joints):
    pos = [pm.xform(node, q=True, ws=True, t=True) for node in joints]
    # We expect the character to be in the standard orientation: Y-up, facing up Z.  Sanity check that
    # the eyes are somewhere up Y.
    if pos[0][1] <= 0 or pos[1][1] <= 0:
        log.error('The selected objects should be on positive Y.')
        return False
            
    # Check that the eyes are parallel on the X axis.
    if abs(pos[0][1] - pos[1][1]) > 0.001 or abs(pos[0][2] - pos[1][2]) > 0.001:
        log.warning('Warning: the selected objects aren\'t parallel on the X axis.')
    return True
		
def set_notes(node, note):
    pm.addAttr(node, sn='nts', ln='notes', dt='string')
    node.attr('notes').set(note, type='string')
	
def create_new_node(nodeType, nodeName=None, parent=None, nonkeyable=True):
    node = pm.createNode(nodeType)

    if 'shape' in pm.nodeType(node, inherited=True):
        # This is a shape node.  Move up to the transform node.
        node = node.getTransform()

    if nodeName:
        node = pm.rename(node, nodeName)

    if parent:
        node = pm.parent(node, parent, r=True)[0]

    if nonkeyable:
        maya_helpers.lock_trs(node, 'unkeyable')

    return node

def create_vector_attribute(node, name):
    pm.addAttr(node, ln=name, at='double3')
    pm.addAttr(node, ln='%sX' % name, at='double', p=name)
    pm.addAttr(node, ln='%sY' % name, at='double', p=name)
    pm.addAttr(node, ln='%sZ' % name, at='double', p=name)

def create_eye_rig():
    selection = pm.ls(sl=True)
    if len(selection) < 2:
        log.warning('Select both eye joints, then an optional control node.')
        return
    joints = selection[0:2]
    
    if not sanity_check_eyes(joints):
        return

    # If a third node is selected, we'll put the distance control attribute on it.
    control_node = None
    if len(selection) >= 3:
        control_node = selection[2]

    # We want the left eye, then the right eye.  Switch them if they're reversed.
    if pm.xform(joints[0], q=True, ws=True, t=True)[0] < pm.xform(joints[1], q=True, ws=True, t=True)[0]:
        joints[0], joints[1] = joints[1], joints[0]
            
    # Search upwards for a shared parent.
    def find_shared_ancestor(node1, node2):
        while True:
            if node1 == node2:
                return node1
            node1 = pm.listRelatives(node1, p=True, pa=True)
            node2 = pm.listRelatives(node2, p=True, pa=True)
            if not node1 or not node2:
                return None
            node1 = node1[0]
            node2 = node2[0]

    joint_parent = find_shared_ancestor(joints[0], joints[1])
#    joint_parent = pm.listRelatives(joints[0], p=True, pa=True)[0]
    if not joint_parent:
        log.error('The selected eye joints don\'t have a shared ancestor.')
        return

    # Get the distance between the eyes, and use a factor of that as the default distance
    # from the eyes to the control.
    left_pos = pm.xform(joints[0], q=True, ws=True, t=True)[0]
    right_pos = pm.xform(joints[1], q=True, ws=True, t=True)[0]
    distance = abs(left_pos - right_pos)
    defaultDistance = distance * 3
    
    # Create the group that will hold the control.  This node sets the origin
    # for the control, and follows the parents of the eye joints (typically the
    # head joint).  We'll put as many nodes in this as possible, to encapsulate
    # what we're creating.
    container_node = create_new_node('transform', nodeName='EyeRig')
    pm.xform(container_node, ws=True, t=average_position(joints[0], joints[1]))
    pm.xform(container_node, ws=True, r=True, t=(0,0,defaultDistance))
    pm.parentConstraint(joint_parent, container_node, mo=True)
    pm.scaleConstraint(joint_parent, container_node, mo=True)
            
    # Create a null centered between the eyes.  This is what the control will aim at.
    center_node = create_new_node('transform', nodeName='Eye_Center', parent=container_node)
    pm.xform(center_node, ws=True, t=average_position(joints[0], joints[1]))

    # Create the handle.
    control_mesh = create_handle('Eyes')
    control_mesh = pm.parent(pm.listRelatives(control_mesh, p=True, pa=True), container_node)[0]
    pm.xform(control_mesh, os=True, t=(0,0,0))
    control_mesh.attr('shape').set(1)
    control_mesh.attr('localRotateX').set(90)
    control_mesh.attr('localScale').set((2, 2, 2))
    control_mesh.attr('v').set(keyable=False, channelBox=True)

    # Set the rotation order to ZXY.  The Z rotation has no effect on the output, since we only
    # connect to X and Y, so this keeps things transforming correctly.
    control_mesh.attr('rotateOrder').set(2)

    # If we weren't given a node to put controls on, put them on the control shape.
    if control_node is None:
        control_node = control_mesh
            
    # Scaling the control won't work as expected, so lock it.  Note that we don't
    # lock rz here, since that confuses the rotation manipulator.
    for lock in 'sx', 'sy', 'sz':
        control_mesh.attr(lock).set(lock=True, keyable=False, cb=False)

    # Create a null inside the handle, and aim constrain it towards the eyes.
    # Create a transform.  Point constrain it to the handle, and aim constrain
    # it to the eyes.  The handle will add the rotation of this transform, so
    # the handle points towards the eyes as it's moved around.
    handle_aim_node = create_new_node('transform', nodeName='EyeRig_HandleAim', parent=container_node)
    pm.pointConstraint(control_mesh, handle_aim_node, mo=False)
    pm.aimConstraint(center_node, handle_aim_node, mo=True)
    set_notes(handle_aim_node, 'This node is aim constrained towards the eyes, and the main control receives this node\'s rotation, so it visually points at the eyes without affecting its rotation.')
    
    # Set the transform of the handle to the rotation of the EyeHandleAim transform, so it's
    # added to the visible rotation of the handle.  We could just connect the rotation to the
    # localRotation of the handle, but we're using that to orient the handle correctly.
    comp_node = create_new_node('composeMatrix', nodeName='EyeRig_CompMatrix1')
    handle_aim_node.attr('rotate').connect(comp_node.attr('inputRotate'))
    comp_node.attr('outputMatrix').connect(control_mesh.attr('transform'))

    # Create a group to hold the eye locators.  This is point constrained to the control.
    eye_locator_group = create_new_node('transform', nodeName='EyeTargets', parent=container_node)
    pm.xform(eye_locator_group, ws=True, t=pm.xform(control_mesh, q=True, ws=True, t=True))
    eye_locator_group.attr('visibility').set(0)
    pm.pointConstraint(control_mesh, eye_locator_group, mo=True)

    # Create locators for the eye targets.  This is what the eyes actually aim towards (via
    # the orient locators).
    eye_locators = []
    for idx, node in enumerate(joints):
        eye_locator = create_new_node('locator', nodeName=['EyeLeft', 'EyeRight'][idx], parent=eye_locator_group)
        pm.xform(eye_locator, ws=True, t=pm.xform(node, q=True, ws=True, t=True))
        pm.xform(eye_locator, ws=True, r=True, t=(0,0,defaultDistance))
        eye_locators.append(eye_locator)

    # Create nulls which will sit on top of the joints.  This is what we'll actually aim,
    # so we can attach any rigging we want to them, and the eye joints only need a simple
    # orient constraint to these.
    orient_locators = []
    for idx, node in enumerate(joints):
        shortName = node.split('|')[-1]
        orient_node = create_new_node('transform', nodeName='%s_Orient' % shortName, parent=container_node)
        pm.xform(orient_node, ws=True, t=pm.xform(node, q=True, ws=True, t=True))

        # Create an up vector for the aim constraint.
        up_node = create_new_node('transform', nodeName='%s_Up' % shortName, parent=container_node)
        pm.xform(up_node, ws=True, t=pm.xform(node, q=True, ws=True, t=True))
        pm.xform(up_node, ws=True, t=(0,1,0), r=True)
    
        # Note that we don't need maintain offset here, only on the final orient constraint.
        # This way, the orient of these is always 0, making it easier to adjust.
        pm.aimConstraint(eye_locators[idx], orient_node, mo=True, worldUpType='object', worldUpObject=up_node)

        # Create a transform inside the orient node.  This rotates along with the control.
        # By making this a child of the top-level orient transform, the aim and the rotation
        # will combine additively.  This is the node we actually orient contrain the eye
        # joints to.
        orient_inner_node = create_new_node('transform', nodeName='%s_OrientInner' % shortName, parent=orient_node)

        # We're going to connect RX and RY to control_mesh, so give this node the same
        # rotation order as control_mesh.
        orient_inner_node.attr('rotateOrder').set(2)
        orient_locators.append(orient_inner_node)

        control_mesh.attr('rotateX').connect(orient_inner_node.attr('rotateX'))
        control_mesh.attr('rotateY').connect(orient_inner_node.attr('rotateY'))

        # Now, create a helper to figure out the X/Y angle.  We don't need this for the eye
        # control itself, since an orient constraint will do that for us, but this gives us
        # a clean rotation value, which driven keys like eyelid controls can be placed against.
        # XXX: This is terrible: a locator to get a vector, two decomposeMatrix nodes to get
        # the world space of the locator and the orient locator, and an expression to call atan2
        # to get the angle.  Also, expressions apparently can't even take vectors as inputs,
        # and they can't read individual values of a matrix.  This is basic trig, how can we
        # do this without all this extra mess?
        attr_name = 'angle_%s' % ['left', 'right'][idx]
        create_vector_attribute(control_mesh, attr_name)
        maya_helpers.lock_attr(control_mesh.attr('%sX' % attr_name), 'unkeyable')
        maya_helpers.lock_attr(control_mesh.attr('%sY' % attr_name), 'unkeyable')
        maya_helpers.lock_attr(control_mesh.attr('%sZ' % attr_name), 'lock')

        forwards_node = create_new_node('locator', nodeName='%s_Forwards' % shortName, parent=orient_inner_node)
        pm.xform(forwards_node, t=(0,0,10), os=True)
        forwards_node.attr('visibility').set(False)

        orient_decompose_node = create_new_node('decomposeMatrix', nodeName='%s_Orient_Decompose' % shortName)
        forwards_decompose_node = create_new_node('decomposeMatrix', nodeName='%s_Forwards_Decompose' % shortName)
        orient_node.attr('worldMatrix[0]').connect(orient_decompose_node.attr('inputMatrix'))
        forwards_node.attr('worldMatrix[0]').connect(forwards_decompose_node.attr('inputMatrix'))

        expr = """
            float $v1X = %(orient_decompose_node)s.outputTranslateX;
            float $v1Y = %(orient_decompose_node)s.outputTranslateY;
            float $v1Z = %(orient_decompose_node)s.outputTranslateZ;
            float $v2X = %(forwards_decompose_node)s.outputTranslateX;
            float $v2Y = %(forwards_decompose_node)s.outputTranslateY;
            float $v2Z = %(forwards_decompose_node)s.outputTranslateZ;

            float $x = $v2X - $v1X;
            float $y = $v2Y - $v1Y;
            float $z = $v2Z - $v1Z;

            %(control_mesh)s.%(attr)sX = -atan2($y, $z) * 180/3.14159;
            %(control_mesh)s.%(attr)sY = atan2($x, $z)* 180/3.14159;
        """
        expr = expr % {
            'orient_decompose_node': orient_decompose_node,
            'forwards_decompose_node': forwards_decompose_node,
            'control_mesh': control_mesh,
            'attr': attr_name,
        }
        pm.expression(s=expr, ae=False, uc='all', o=control_mesh)
        
    # Constrain the eye joints to the orient transform.
    for idx, node in enumerate(joints):
        pm.orientConstraint(orient_locators[idx], joints[idx], mo=True)
    
    # Create a setRange node.  This will translate from the eye locator X position (distance from
    # the center to the locator) to a 0..1 range that can be used as a control.
    #
    # setRange nodes actually clamp to their min and max, rather than just adjusting the range.
    # We don't really want that, since it can be useful to set the distance to a slightly negative
    # number to move the eyes apart a bit.  Work around this: instead of scaling 0..1 to eyeLocatorXPos..0,
    # scale from -1..1 to eyeLocatorXPos*2..0.  This gives a wider range, if wanted.
    # In:  -5 -4 -3 -2 -1  0  1  2  3  4  5
    # Out:  6  5  4  3  2  1  0 -1 -2 -3 -4
    locator_distance_range = create_new_node('setRange', nodeName='EyeRig_SetRangeEyeDistance')
    eye_locator1_x = pm.xform(eye_locators[0], q=True, t=True, os=True)[0]
    eye_locator2_x = pm.xform(eye_locators[1], q=True, t=True, os=True)[0]
    locator_distance_range.attr('oldMin').set((-5, -5, 0))
    locator_distance_range.attr('oldMax').set((5, 5, 0))
    locator_distance_range.attr('min').set((eye_locator1_x*6, eye_locator2_x*6, 0))
    locator_distance_range.attr('max').set((eye_locator1_x*-4, eye_locator2_x*-4, 0))

    # The output of the setRange controls the distance of the eye locator from the main center control.
    locator_distance_range.attr('outValueX').connect(eye_locators[0].attr('translateX'))
    locator_distance_range.attr('outValueY').connect(eye_locators[1].attr('translateX'))

    # Add an attribute to move the eye locators to the center.  The most useful values of this are
    # 0 and 1, but support moving further and going crosseyed.
    pm.addAttr(control_node, ln='EyesFocused', at='double', min=-5, max=5, dv=0)
    control_node.attr('EyesFocused').set(e=True, keyable=True)
    control_node.attr('EyesFocused').connect(locator_distance_range.attr('valueX'))
    control_node.attr('EyesFocused').connect(locator_distance_range.attr('valueY'))

    # Move the control mesh to the top of the container.
    pm.reorder(control_mesh, front=True)
    pm.select(control_mesh)
    return container_node

