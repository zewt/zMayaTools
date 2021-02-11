import pymel.core as pm
import maya.cmds as cmds
from maya import OpenMaya as om
from zMayaTools import maya_helpers, command

from zMayaTools import maya_logging
log = maya_logging.get_log()

# There's no way to query if moveJointsMode is enabled, so we have to track it ourselves.
move_skinned_joints_enabled = False

class MoveSkinnedJoints(command.Command):
    cmd = 'zMoveSkinnedJoints'

    @classmethod
    def create_syntax(cls):
        syntax = om.MSyntax()
        syntax.enableQuery(True)
        syntax.addFlag('-en', '-enable', om.MSyntax.kBoolean)
        syntax.addFlag('-t', '-toggle')
        return syntax

    def __init__(self):
        super(MoveSkinnedJoints, self).__init__()
        self.previous_state = move_skinned_joints_enabled

    def doIt(self, args):
        self.data = self.args(args)
        if self.data is None:
            return

        self.redoIt()

    def redoIt(self):
        if self.data.isFlagSet('-toggle'):
            self.set_enabled(not move_skinned_joints_enabled)
        elif self.data.isFlagSet('-enable'):
            if self.data.isQuery():
                self.setResult(move_skinned_joints_enabled)
                return

            enable = self.data.flagArgumentBool('-enable', 0)
            self.set_enabled(enable)

    def undoIt(self):
        with maya_helpers.without_undo():
            self.set_enabled(self.previous_state)

    def set_enabled(self, value):
        global move_skinned_joints_enabled
        move_skinned_joints_enabled = value

        # Disable undo while we do this, so these commands don't create their own
        # undo chunk, which causes redoing to clear the redo queue.  This is safe
        # since we'll explicitly handle undo in undoIt.
        with maya_helpers.without_undo():
            # Note that there's no query for moveJointsMode.
            nodes = pm.ls(type='skinCluster')
            for node in nodes:
                pm.skinCluster(node, e=True, moveJointsMode=value)

        if value:
            pm.inViewMessage(statusMessage='Move skinned joints mode active', pos='botCenter')
        else:
            pm.inViewMessage(clear='botCenter')

        self.undoable = True

def _get_nodes_depth_first(all_nodes):
    """
    Return all_nodes, placing parent nodes earlier in the list than their children.
    """
    all_nodes = set(all_nodes)
    node_parents = {node: node.getParent() for node in all_nodes}

    result = []
    def add_starting_at(node):
        # Make sure the node's parent has been added first.
        parent = node_parents[node]
        if parent in all_nodes:
            add_starting_at(parent)

        # If this node's parent isn't in node_parents, add it.
        result.append(node)
        all_nodes.remove(node)

    while all_nodes:
        add_starting_at(next(iter(all_nodes)))

    return result

def _get_skin_cluster_attrs_for_joint(joint):
    # Get the skinCluster matrix connections for this joint.
    attrs = joint.worldMatrix[0].listConnections(s=False, d=True, type='skinCluster', p=True)

    # We only care about matrix connections.
    attrs = [attr for attr in attrs if attr.attrName(longName=True) == 'matrix']
    return attrs

def _connect_or_lock(src, dst):
    """
    Connect src to dst if possible.  Otherwise, lock src.
    """
    if dst.isConnected() or dst.isLocked():
        src.set(lock=True)
    else:
        src.connect(dst)

def _lock_transform(node):
    for attr in ('translate', 'rotate', 'scale', 'shear', 'rotateOrder', 'rotateAxis', 'jointOrient'):
        if node.hasAttr(attr):
            node.attr(attr).set(lock=True)

@maya_helpers.py2melProc(procName='zCreateEditableJoints')
def create_editable_joints():
    """
    Create a proxy skeleton that can be used to edit bound joint positions.
    """
    selection = pm.ls(sl=True, type='transform')
    if len(selection) == 0:
        log.info('Select one or more root joints')
        return

    # Get the hierarchy of all selected nodes.
    bind_joints = []
    for node in selection:
        bind_joints.append(node)
        bind_joints.extend(pm.listRelatives(node, ad=True))

    # Order them parents-first.  This will also remove any duplicates.
    bind_joints = _get_nodes_depth_first(bind_joints)

    any_errors = False
    for bind_joint in bind_joints:
        if om.MVector(bind_joint.rotate.get()).length() > 0.0001:
            log.error('Joint %s has nonzero rotations', bind_joint.nodeName())
            any_errors = True

        # Make sure that all joints are in bind position for all skinClusters they're
        # connected to.
        bind_joint_skin_cluster_attrs = _get_skin_cluster_attrs_for_joint(bind_joint)
        for skin_cluster_attr in bind_joint_skin_cluster_attrs:
            # Get this joint's bindPreMatrix on this skinCluster, and make sure that it's
            # the same as the current world matrix's inverse.
            skin_cluster = skin_cluster_attr.node()
            skin_cluster_idx = skin_cluster_attr.index()

            bind_pre_matrix = pm.datatypes.Matrix(skin_cluster.bindPreMatrix[skin_cluster_idx].get())
            world_inverse_matrix = pm.datatypes.Matrix(bind_joint.worldInverseMatrix.get())
            if not bind_pre_matrix.isEquivalent(world_inverse_matrix, tol=0.0001):
                log.error('Joint %s isn\'t in bind position for %s', bind_joint.nodeName(), skin_cluster_attr.name())
                any_errors = True

    if any_errors:
        return

    _fix_skin_cluster_disconnection()

    # Create a top-level group to hold everything.
    edit_container = pm.createNode('transform', n='EditJoints')
    edit_container.inheritsTransform.set(False)
    _lock_transform(edit_container)

    bind_joint_to_edit_joint = {}
    for bind_joint in bind_joints:
        # If this isn't a joint, and it has no DAG children, skip it.  This prevents
        # duplicating things like constraints, which is harmless but can be confusing.
        if not isinstance(bind_joint, pm.nodetypes.Joint) and len(bind_joint.getChildren()) == 0:
            continue

        # Duplicate the transform, without its its hierarchy or any shape nodes inside it.
        edit_joint = pm.duplicate(bind_joint, parentOnly=True)[0]
        pm.rename(edit_joint, 'Edit_%s' % bind_joint.nodeName())
        edit_joint.visibility.set(True)
        bind_joint_to_edit_joint[bind_joint] = edit_joint

        # Place it in the corresponding parent.
        bind_joint_parent = bind_joint.getParent()
        edit_joint_parent = bind_joint_to_edit_joint.get(bind_joint_parent)
        if not edit_joint_parent:
            # If this joint's parent isn't in bind_joints, create a parent matching the joint's
            # parent, to match the joint's coordinate space.
            assert bind_joint_parent not in bind_joints
            edit_joint_parent = pm.createNode('transform', n='EditJoints_%s' % bind_joint.nodeName(), p=edit_container)
            pm.xform(edit_joint_parent, ws=True, m=pm.xform(bind_joint_parent, q=True, ws=True, m=True))
            _lock_transform(edit_joint_parent)

        pm.parent(edit_joint, edit_joint_parent, r=True)

        # If this isn't a joint, we're just copying it to match the transformation
        # hierarchy and won't edit it.  Lock its transform properties and don't do anything
        # else with it.
        if not isinstance(edit_joint, pm.nodetypes.Joint):
            _lock_transform(edit_joint)
            continue

        # The two skeletons are in the same place, and since we're binding to world space
        # transforms we can't put the edit skeleton off to the side.  Increase the joint
        # radius slightly so they don't draw exactly on top of each other.  Set an object
        # color, too.
        edit_joint.radius.set(edit_joint.radius.get() * 1.25)
        edit_joint.useObjectColor.set(True)
        edit_joint.objectColor.set(7)

        joint_matrix_before_edits = pm.datatypes.Matrix(pm.xform(edit_joint, q=True, ws=True, m=True))

        # Transfer the joint's rotation from jointOrient to rotate.
        edit_joint.rotate.set(edit_joint.jointOrient.get())
        edit_joint.jointOrient.set((0,0,0))

        # jointOrient is always in rotate order XYZ, not the transform's rotateOrder, so
        # change the joint's rotateOrder to xyz.
        edit_joint.rotateOrder.set(0)

        # Lock transform properties that shouldn't be edited.  Editing these would modify
        # the matrix we're sending to the skinCluster without making a corresponding change
        # to the joint.
        for attr in ('scale', 'rotateOrder', 'rotateAxis', 'jointOrient'):
            edit_joint.attr(attr).set(lock=True)

        joint_matrix_after_edits = pm.datatypes.Matrix(pm.xform(edit_joint, q=True, ws=True, m=True))

        # Verify that our changes to the edit joint retained the same world matrix.
        assert joint_matrix_before_edits.isEquivalent(joint_matrix_after_edits), bind_joint

        # When we duplicate a joint, its inverseScale is connected to its nearest ancestor joint's
        # scale, not whatever the joint we duplicated had its inverseScale set to.  It usually gives
        # the same connection, but doesn't have to, which can make our duplicated joint's segment
        # scale compensate behave differently.  We don't want this connected anyway, since any
        # scale changes are caused by animation and shouldn't apply to the edit joints.  Just
        # disconnect any inverseScale connection, and set its value to the same value as the bind
        # joint.
        conns = pm.listConnections(edit_joint.inverseScale, s=True, d=False, p=True)
        if conns:
            conns[0].disconnect(edit_joint.inverseScale)
        edit_joint.inverseScale.set(bind_joint.inverseScale.get())

        # Editing the edit joint's translation changes the bind joint's translation.
        # If any part of translation is connected or locked on the joint, lock it on
        # the edit joint.
        if bind_joint.translate.isConnected() or bind_joint.translate.isLocked():
            edit_joint.translate.set(lock=True)
        else:
            for attr in ('tx', 'ty', 'tz'):
                _connect_or_lock(edit_joint.attr(attr), bind_joint.attr(attr))

        # Editing rotation changes its jointOrient.
        _connect_or_lock(edit_joint.rotate, bind_joint.jointOrient)

        bind_joint_skin_cluster_attrs = _get_skin_cluster_attrs_for_joint(bind_joint)
        for skin_cluster_attr in bind_joint_skin_cluster_attrs:
            skin_cluster = skin_cluster_attr.node()
            skin_cluster_idx = skin_cluster_attr.index()

            bind_pre_matrix = pm.datatypes.Matrix(skin_cluster.bindPreMatrix[skin_cluster_idx].get())
            world_inverse_matrix = pm.datatypes.Matrix(bind_joint.worldInverseMatrix.get())

            # Moving the edit joint around edits the bind position of the bind joint.
            edit_joint.worldInverseMatrix.connect(skin_cluster.bindPreMatrix[skin_cluster_idx])

    pm.select(edit_container)
    return edit_container

def _fix_skin_cluster_disconnection():
    """
    The bindPreMatrix attribute of skinClusters has a bug: its disconnect behavior is
    set to kDelete instead of kNothing.  This means that when our edit joints are disconnected,
    deleted, or simply undone, the bindPreMatrix entry goes away and the skinCluster breaks.

    Work around this by editing the attribute directly to fix the disconnection behavior.
    """
    # We need a skinCluster to get a reference to the bindPreMatrix attribute.  Just
    # create a temporary one.
    skin_cluster = pm.createNode('skinCluster', skipSelect=True)
    try:
        # Get the underlying attribute for bindPreMatrix.
        bind_pre_matrix_plug = skin_cluster.bindPreMatrix.__apimplug__()
        bind_pre_matrix_attr = om.MFnAttribute(bind_pre_matrix_plug.attribute())

        # Change its disconnectBehavior to kNothing.
        bind_pre_matrix_attr.setDisconnectBehavior(2)
    finally:
        pm.delete(skin_cluster)

