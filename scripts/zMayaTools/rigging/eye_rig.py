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
    maya_helpers.load_plugin('zRigHandle')
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
    if not joint_parent:
        log.error('The selected eye joints don\'t have a shared ancestor.')
        return

    # Get the distance between the eyes, and use a factor of that as the default distance
    # from the eyes to the control.
    left_pos = pm.xform(joints[0], q=True, ws=True, t=True)[0]
    right_pos = pm.xform(joints[1], q=True, ws=True, t=True)[0]
    distance = abs(left_pos - right_pos)
    defaultDistance = distance * 2
    
    # Create the group that will hold the control.  This node sets the origin for the control,
    # and follows the parents of the eye joints (typically the head joint).  This is positioned
    # at the head, but we set its world space rotation to identity, so the rig is always oriented
    # the same way and not in the head's local orientation.
    container_node = create_new_node('transform', nodeName='EyeRig')
    joint_parent.worldMatrix[0].connect(container_node.offsetParentMatrix)
    pm.xform(container_node, ws=True, ro=(0,0,0))
    container_node.inheritsTransform.set(False)
            
    # Create a null centered between the eyes.  This is what the control will aim at.
    center_node = create_new_node('transform', nodeName='Eye_Center', parent=container_node)
    pm.xform(center_node, ws=True, t=average_position(joints[0], joints[1]))

    # Create the handle.
    control_mesh = create_handle('Eyes')
    control_mesh = pm.parent(pm.listRelatives(control_mesh, p=True, pa=True), container_node, r=True)[0]
    control_mesh.shape.set(1)
    control_mesh.localRotateX.set(90)
    control_mesh.localScale.set((2, 2, 2))
    control_mesh.visibility.set(keyable=False, channelBox=True)

    # Center the handle between the eyes, then move it forward.
    pm.xform(control_mesh, ws=True, t=average_position(joints[0], joints[1]))
    pm.xform(control_mesh, ws=True, r=True, t=(0,0,defaultDistance))

    # Put the base transform in offsetParentMatrix, so the control's TRS is zero.
    control_mesh.offsetParentMatrix.set(control_mesh.matrix.get())
    control_mesh.t.set((0,0,0))

    # Combine the control transform's offsetParentMatrix and matrix.  This is the actual position
    # of the control within the coordinate space of the rig.
    control_transform = pm.createNode('multMatrix', n='EyeRig_ControlTransform')
    control_mesh.matrix.connect(control_transform.matrixIn[0])
    control_mesh.offsetParentMatrix.connect(control_transform.matrixIn[1])
    control_mesh_matrix = control_transform.matrixSum

    # Set the rotation order to ZXY.  We're only rotating on X and Y, so putting Z first
    # means we can ignore it without affecting the result.
    control_mesh.rotateOrder.set(2)

    # If we weren't given a node to put controls on, put them on the control shape.
    if control_node is None:
        control_node = control_mesh
            
    # Scaling the control won't work as expected, so lock it.  Note that we don't
    # lock rz here, since that confuses the rotation manipulator.
    for lock in 'sx', 'sy', 'sz':
        maya_helpers.lock_scale(control_mesh, lock='hide')

    # Create a matrix that aims the translation control towards the center of the eyes.
    # This gives us the rotation caused by translating the control.
    aim_matrix = pm.createNode('aimMatrix', n='EyeRig_HandleAim')
    aim_matrix.primaryInputAxis.set((0,0,-1))

    # If we leave secondaryInputAxis disabled, the aimMatrix will aim the X and Y axes and pass
    # through Z (twist).  Align the twist axis to zero it out.
    aim_matrix.secondaryInputAxis.set((0,1,0))
    aim_matrix.secondaryTargetVector.set((0,1,0))
    aim_matrix.secondaryMode.set(2) # align
    control_mesh_matrix.connect(aim_matrix.inputMatrix)
    center_node.matrix.connect(aim_matrix.primaryTargetMatrix)

    # The aimMatrix includes the translation, which is a bit weird.  It's an aim matrix, why
    # would you want it to include translation?  Use pickMatrix to grab just rotation.
    pick_rotation = pm.createNode('pickMatrix', n='EyeRig_PickAimRotation')
    pick_rotation.useTranslate.set(False)
    pick_rotation.useScale.set(False)
    pick_rotation.useShear.set(False)
    aim_matrix.outputMatrix.connect(pick_rotation.inputMatrix)

    translation_rotation_matrix = pick_rotation.outputMatrix

    # Rotate the handle with the aim matrix, so it points towards the eyes when it's translated around.
    # This is purely cosmetic.
    translation_rotation_matrix.connect(control_mesh.transform)

    # Create a setRange node to scale the eyesFocused value to an angle.
    locator_distance_range = create_new_node('setRange', nodeName='EyeRig_SetRangeEyeDistance')
    locator_distance_range.oldMin.set((-5, -5, 0))
    locator_distance_range.oldMax.set((5, 5, 0))
    locator_distance_range.min.set((30, -30, 0))
    locator_distance_range.max.set((-30, 30, 0))

    # Add an attribute to move the eyes inwards and outwards.
    pm.addAttr(control_node, ln='eyesFocused', at='double', min=-5, max=5, dv=0)
    control_node.eyesFocused.set(e=True, keyable=True)
    control_node.eyesFocused.connect(locator_distance_range.valueX)
    control_node.eyesFocused.connect(locator_distance_range.valueY)

    for idx, node in enumerate(joints):
        shortName = node.nodeName(stripNamespace=True)

        # Extract the rotation part of the eye transform.  We could use .rotate, but we'd need to compose it
        # to a matrix anyway, so this is faster and doesn't care about rotation order.
        pick_rotation = pm.createNode('pickMatrix', n='PickTransformRotation_%s' % shortName)
        pick_rotation.useTranslate.set(False)
        pick_rotation.useScale.set(False)
        pick_rotation.useShear.set(False)
        control_mesh_matrix.connect(pick_rotation.inputMatrix)

        # Compose the eyesFocused value, which also contributes to the rotation.
        eyes_focused_compose = pm.createNode('composeMatrix', n='EyeRig_ComposeFocusedMatrix_%s' % shortName)
        focused_angle = [locator_distance_range.outValueX, locator_distance_range.outValueY][idx]
        focused_angle.connect(eyes_focused_compose.inputRotateY)

        # Finally, combine the three parts of the rotation.
        combine_rotations = pm.createNode('multMatrix', n='EyeRig_CombineRotations_%s' % shortName)
        translation_rotation_matrix.connect(combine_rotations.matrixIn[0])
        pick_rotation.outputMatrix.connect(combine_rotations.matrixIn[1])
        eyes_focused_compose.outputMatrix.connect(combine_rotations.matrixIn[2])

        # Decompose the result back to euler rotations and connect it to the angle attribute.
        # We're only rotating on X and Y, and putting Z first so it doesn't affect the others.
        # Only connect X and Y so any rotations on Z are discarded.
        decompose_rotation = pm.createNode('decomposeMatrix', n='EyeRig_DecomposeFinalRotations_%s' % shortName)
        decompose_rotation.inputRotateOrder.set(2) # zxy
        combine_rotations.matrixSum.connect(decompose_rotation.inputMatrix)

        # Create a node that will receive the final rotation, and constrain the joint to it.
        output_node = create_new_node('transform', nodeName='%s_Output' % shortName, parent=container_node)
        pm.xform(output_node, ws=True, t=pm.xform(node, q=True, ws=True, t=True))
        decompose_rotation.outputRotateX.connect(output_node.rotateX)
        decompose_rotation.outputRotateY.connect(output_node.rotateY)
        output_node.rotateOrder.set(2)
        pm.orientConstraint(output_node, joints[idx], mo=True)

    # Move the control mesh to the top of the container.
    pm.reorder(control_mesh, front=True)
    pm.select(control_mesh)
    return container_node

