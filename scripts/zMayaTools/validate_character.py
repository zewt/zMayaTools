import math, time
import pymel.core as pm
from maya import cmds
from maya import OpenMaya as om

from zMayaTools import maya_helpers, maya_logging
log = maya_logging.get_log()

# This runs a number of sanity checks.  It's intended to be used against character meshes
# that are symmetric across the YZ plane.
#
# - Nonmanifold vertices and lamina edges
# - Only one history mesh.  More than one mesh in history often indicates that construction
# history has been left behind unintentionally.
# - No vertex tweaks on the output mesh.  This can happen if the output mesh is modified, and
# can result in a bad export.
# - No vertex tweaks on the mesh or on a tweak node.  These are mostly harmless, but can
# make some operations not work, such as connecting a temporary mesh's outMesh to the inMesh
# of the base mesh to copy data.
# - The current output mesh is identical to the base mesh.  If the mesh isn't identical,
# something in the rigging is changing it.  Most character meshes should be identical to
# their base mesh when in bind pose.  (However, things like IK and HumanIK can cause this
# to not happen.)
# - Meshes are topologically symmetric around edges on the YZ plane.  This is tested
# by attempting to activate topological symmetry (there's no API exposed for this).
# - Mesh vertices are symmetric in world space across the YZ plane.
# 
# If the mesh has a skeleton, these checks are performed.  Note that most checks are
# only performed on joints that are bound to the selected mesh, and helper joints in
# the skeleton that aren't bound are ignored.
# 
# - The current pose of the skeleton matches the pose the skeleton was in at bind time.
# This doesn't depend on a bindPose.
# - The geometry transform matches what it was at bind time.
# - Stub joints (non-bound leaf joints) have a zero transform.  Orient joints tends to
# give these a weird orientation.
# - The rotation of all joints is zero.
# - All joints have labels.  This is very helpful for skin mirroring and copying, and
# is used for the remaining symmetry checks.
# - Except for left/right symmetric joints, labels aren't duplicated.  Maya may be able
# to figure out duplicated joints based on the hierarchy, but that logic isn't exposed to
# us, so we require unique labels.  For things like finger joints where Maya doesn't provide
# enough labels, use "Other" and set the label directly.
# - Joints labelled left/right have a matching labelled joint on the other side.  Joints
# labeleld "center" are at X = 0.  If you have joints that are asymmetric (no matching joint
# and also not in the center), set them to side "None".
# - Symmetric joints have symmetric positions and rotations, and have the same rotateOrder.
# - Vertices aren't weighted to more than 4 vertices.
# 
# XXX: Check UV overlapping.  The UV editor shows this.  How can we use that?
# XXX: Check UV tiling.  UVs may use multiple tiles, but should only use positive tiles
# since negative tiles cause ugly tile filenames.
# XXX: Add a way to silence warnings by adding an attribute to meshes.

# Constants for pm.polySelectConstraint:
constraint_vertex = 0x0001
constraint_edge = 0x8000
constraint_face = 0x0008
constraint_uv = 0x0010

def get_vertices(mesh):
    # Meshes with no data can either crash during pm.xform or raise an exception.
    try:
        if not len(mesh.vtx):
            log.warning('Warning: mesh %s has no vertices', mesh.nodeName())
            return []
    except pm.MayaComponentError:
        log.warning('Warning: mesh %s has no vertices', mesh.nodeName())
        return []

    # Pymel's getPoints is frighteningly slow, so we use pm.xform instead.
    points = pm.xform(mesh.vtx, q=True, t=True)    
    points = [(x, y, z) for x, y, z, in zip(points[0::3], points[1::3], points[2::3])]

    # This is convenient, but slow.
#    points = [om.MPoint(x, y, z) for x, y, z, in zip(points[0::3], points[1::3], points[2::3])]
    return points

def get_distance(p1, p2):
    x = p1[0] - p2[0]
    y = p1[1] - p2[1]
    z = p1[2] - p2[2]
    return math.pow(x*x+y*y+z*z, .5)

def format_pos(pos):
    return '%.4f %.4f %.4f' % (pos[0], pos[1], pos[2])

class Validate(object):
    def __init__(self, config, node, progress):
        self.config = config
        self.node = node
        self.progress = progress
        self.warnings = []

    def log(self, s, nodes=None):
        """
        Add a validation warning.

        If nodes isn't None, it's a list of nodes to select that are related to the warning.
        """
        # nodes may be a list or a preformatted string.
        if isinstance(nodes, list):
            nodes = ' '.join(str(s) for s in nodes)

        self.warnings.append({
            'msg': s,
            'nodes': nodes,
        })

    def check_identical_to_orig(self, base_points, output_points):
        """
        Verify that two meshes are identical.

        This is used to verify that the current output mesh is identical to the base mesh.  If this
        reports a warning, deformers on the mesh are changing it even though it's in bind pose.
        """
        if len(base_points) != len(output_points):
            self.log('Output mesh has a different number of output vertices (%i) than base vertices (%i).  Is there topology-modifying history?' %
                (len(base_points), len(output_points)),
                nodes=[self.node])
            return

        # Count the number of vertices that are in a different place in the output mesh than the input mesh
        # by different levels of error.
        vtxs_0001 = []
        vtxs_001 = []
        vtxs_01 = []
        cnt_0001 = 0
        cnt_001 = 0
        cnt_01 = 0
        for idx in xrange(len(base_points)):
            p1 = base_points[idx]
            p2 = output_points[idx]
            distance = get_distance(p1, p2)
            if     distance > 0.01:    vtxs_01.append(idx)
            elif  distance > 0.001:   vtxs_001.append(idx)
            elif distance > 0.0001:  vtxs_0001.append(idx)

        vertices = str(self.node.getShape())

        if len(vtxs_01) > 0:
            self.log('Output mesh is different than input mesh by 0.01: %i' % len(vtxs_01),
                    nodes=' '.join('%s.vtx[%i]' % (vertices, idx) for idx in vtxs_01))
        if len(vtxs_001) > 0:
            self.log('Output mesh is different than input mesh by 0.001: %i' % len(vtxs_001),
                    nodes=' '.join('%s.vtx[%i]' % (vertices, idx) for idx in vtxs_001))
        if len(vtxs_0001) > 0:
            self.log('Output mesh is different than input mesh by 0.0001: %i' % len(vtxs_0001),
                    nodes=' '.join('%s.vtx[%i]' % (vertices, idx) for idx in vtxs_0001))

    def check_tweak_node(self):
        """
        Verify that a mesh has no modifications on its tweak node.

        This may indicate that the mesh was sculpted unintentionally when a blend shape was
        meant to be sculpted.
        """
        tweak_nodes = self.node.listHistory(type='tweak', pruneDagObjects=True)
        if len(tweak_nodes) >= 2:
            self.log('Mesh has more than one tweak node', nodes=tweak_nodes)

        for tweak_node in tweak_nodes:
            tweaked_vertices = []
            vlist = tweak_node.attr('vlist').elementByLogicalIndex(0).attr('vertex')
            for tweak in vlist:
                if om.MVector(*tweak.get()).length() > 0.000001:
                    tweaked_vertices.append(tweak.index())
            if tweaked_vertices:
                shape_name = self.node.getShape()
                verts = ' '.join('%s.vtx[%i]' % (shape_name, idx) for idx in tweaked_vertices)
                self.log('Mesh has %i %s on its tweak node %s' % (len(tweaked_vertices), 'modification' if len(tweaked_vertices) == 1 else 'modifications',
                    tweak_node.nodeName()), nodes=verts)

    def check_overlapping_vertices(self):
        """
        Verify that meshes have no overlapping vertices.

        Note that this will fail if the overlap threshold is so high that all vertices are
        merged, since polyMergeVert will fail with a "Can't perform polyMergeVert on selection"
        error.
        """
        shape = self.node.getShape()

        # Delete any nodes created while doing this when we're done.
        with maya_helpers.temporary_namespace():
            # Create a polyMergeVert to remove overlapping vertices, outputting to a temporary mesh.
            merge_vert = pm.createNode('polyMergeVert', name='TempMergeVert')
            merge_vert.inputComponents.set((1, 'vtx[*]'), type='componentList')
            merge_vert.distance.set(self.config['vertex_overlap_threshold'])
            temp_mesh = pm.createNode('mesh', name='TempMesh')
            shape.outMesh.connect(merge_vert.inputPolymesh, force=True)

            # Why does mesh.inMesh print a "Defaulting to MFnDagNode" warning?
            # merge_vert.attr('output') #.connect(temp_mesh.inMesh)
            cmds.connectAttr(str(merge_vert.output), '%s.inMesh' % temp_mesh.name())

            # polyMergeVert always removes vertices without reordering them, so we can figure out which
            # vertices were actually removed by walking through both vertex lists in order.  This won't
            # tell us which vertex it matched against, but it'll give enough information for us to highlight
            # the problem.
            output_vtx_idx = 0
            missing_vertices = []
            input_vertices = get_vertices(shape)
            output_vertices = get_vertices(temp_mesh)
            for input_vtx_idx, input_vtx in enumerate(input_vertices):
                # If we've run out of output vertices, all remaining input vertices are missing.
                if output_vtx_idx >= len(output_vertices):
                    missing_vertices.append(shape.vtx[input_vtx_idx])
                    continue

                output_vtx = output_vertices[output_vtx_idx]
                distance = get_distance(input_vtx, output_vtx)
                if distance > 0.00001:
                    # This input vertex is missing.
                    missing_vertices.append(shape.vtx[input_vtx_idx])
                    continue

                output_vtx_idx += 1

            if missing_vertices:
                self.log('Mesh has %i overlapping %s.' %
                        (len(missing_vertices), 'vertex' if len(missing_vertices) == 1 else 'vertices'),
                        nodes=missing_vertices)

    def check_vertex_tweaks(self, base=True):
        """
        Verify that a mesh has no vertex tweaks.

        If a mesh is modified when it has no deformers (no tweak node), changes are stored as vertex
        tweaks instead of applied to the vertex data itself.  This is usually harmless, but can complicate
        later edits.  Once a mesh is stable and not being edited, vertex tweaks can be baked to the vertices
        with the polyCollapseTweaks command.  Note that this will create a history node which should be
        deleted.
        """
        shapes = self.node.getShapes()
        if base:
            if len(shapes) < 2:
                # This mesh has no history.
                return

            base_mesh = shapes[-1]
        else:
            base_mesh = shapes[0]

        tweaks = base_mesh.attr('pt')
        tweaked_vertices = []
        for tweak in tweaks:
            idx = tweak.index()

            # twaek.get() should return the vector, but in some cases at least with deformed
            # meshes it always returns (0,0,0).
            x = tweak.attr('pntx').get()
            y = tweak.attr('pnty').get()
            z = tweak.attr('pntz').get()
            vec = om.MVector(x, y, z)
            if om.MVector(vec).length() > 0.000001:
                tweaked_vertices.append(tweak.index())

        if tweaked_vertices:
            shape_name = self.node.getShape()
            verts = ' '.join('%s.vtx[%i]' % (shape_name, idx) for idx in tweaked_vertices)
            
            if base:
                self.log('The base mesh has %i vertex %s.  This can be baked with the polyCollapseTweaks command.' %
                        (len(tweaked_vertices), 'tweak' if len(tweaked_vertices) == 1 else 'tweaks'),
                        nodes=verts)
            else:
                self.log('The output mesh has %i vertex %s.' %
                        (len(tweaked_vertices), 'tweak' if len(tweaked_vertices) == 1 else 'tweaks'),
                        nodes=verts)

    def check_history(self):
        """
        Check for unwanted nodes in the mesh history.

        This is tricky, since nodes can be used in endless ways to rig meshes, but there are also
        a lot of unintentional cases we can check.  For example, polyTweakUV nodes in history usually
        either mean there's history to be deleted (if it's near the front of the chain), or UVs were
        accidentally edited on the output mesh instead of the base mesh (if it's near the end of the
        chain).  Both of these are important to flag.
        """
        # Don't list history from the output mesh backwards, since that'll traverse into joints and
        # who knows what from there.  Instead, list the future from the base mesh forwards.
        shapes = self.node.getShapes()
        base_mesh = shapes[-1]

        # Node types that we know are good.  We won't warn about these.
        known_good_node_types = [
            pm.nodetypes.GroupParts,
            pm.nodetypes.Tweak,

            # Mesh, etc:
            pm.nodetypes.GeometryShape,

            # This includes all regular deformers, like skinCluster.
            pm.nodetypes.GeometryFilter,

            # listFuture is traversing message connections, which pulls in a lot of noise.  There's
            # also no way to get the relevant plugs, like you can with listConnections.  How do we
            # get only shape/deformer history?
            pm.nodetypes.NodeGraphEditorInfo,

            # Whitelist polyMoveUV.  It's a polyModifier, which is in the bad node list, but it's useful
            # to rig UVs, and it doesn't seem to be generated by regular edits (moving UVs generates polyTweakUV).
            pm.nodetypes.PolyMoveUV,

            # This is created by sculpt freezing.
            pm.nodetypes.CreateColorSet,

            # We can see these if the base mesh has materials attached.
            pm.nodetypes.ShadingEngine,
        ]

        # Node types that are usually bad.
        known_bad_node_types = [
            # polyModifier includes things like polyTweakUV.  These aren't always unwanted.  For example,
            # polyMoveUV is useful for rigging UVs.  We'll assume these are unwanted if they're after deformers.
            pm.nodetypes.PolyModifier,
        ]

        for history_node in pm.listFuture(base_mesh):
            # Stop when we reach the output node, so we don't traverse into anything reading it, like
            # pointOnPoly constraints and wrap deformers.
            if history_node == shapes[0]:
                break

            # Ignore any nodes on the good node list.
            if any(isinstance(history_node, node_type) for node_type in known_good_node_types):
                continue

            is_bad = any(isinstance(history_node, node_type) for node_type in known_bad_node_types)
            if is_bad:
                self.log('Probably unwanted history node: %s (%s)' % (history_node, history_node.type()), nodes=[history_node])
            else:
                # Make a note of nodes we don't handle, so we can add them to the correct list.
                self.log('Unknown history node: %s (%s)' % (history_node, history_node.type()), nodes=[history_node])

        # Normally, the output mesh is the first shape on the transform, and all other meshes
        # are intermediate.  Lots of things in Maya depend on this.  For example, polyListComponentConversion
        # doesn't work and check_topological_symmetry will fail in confusing ways.
        shapes = self.node.getShapes()
        if shapes[0].intermediateObject.get():
            self.log('First shape node shouldn\'t be intermediate', nodes=[shapes[0]])
        for shape in shapes[1:]:
            if not shape.intermediateObject.get():
                self.log('All shape nodes except the first should be intermediate', nodes=[shape])

    def check_topological_symmetry(self, shape, vertices):
        # We expect the mesh to be symmetric across the YZ plane.  Find vertices along it.
        vertices_on_symmetry_plane = []
        for idx, vert in enumerate(vertices):
            if abs(vert[0]) < 0.001:
                vertices_on_symmetry_plane.append(idx)

        if not vertices_on_symmetry_plane:
            self.log('Mesh isn\'t topologically symmetric (no vertices found on the YZ plane)', nodes=[self.node])
            return

        # We need a list of vertices to pass to polyListComponentConversion.  shape.vtx[idx] gives us it,
        # but that's very slow.  It's much faster to just give a list of component path strings.
        verts = ['%s.vtx[%i]' % (shape.name(), idx) for idx in vertices_on_symmetry_plane]

        # Find edges connecting vertices on the YZ plane.  These should all be valid edges for topological
        # symmetry.
        symmetry_edges = pm.polyListComponentConversion(verts, toEdge=True, internal=True)

        if not symmetry_edges:
            self.log('Mesh isn\'t topologically symmetric (no edges found on the YZ plane)', nodes=[self.node])
            return
        # symmetry_edges is a list of component sets.  Use the first entry in the first set.
        symmetry_edge = pm.ls(symmetry_edges[0])[0].currentItem()

        # Try to activate symmetry.  This will fail if the mesh isn't topologically symmetric around the
        # selected edge.  Unfortunately, this will also print an error and raise an exception instead of
        # just returning whether it succeeded.  There doesn't seem to be any direct API for topo symmetry.
        try:
            pm.symmetricModelling(symmetry_edge, topoSymmetry=True)
        except RuntimeError as e:
            self.log('Mesh isn\'t topologically symmetric (selected %s as symmetry edge)' % symmetry_edge, nodes=[self.node])
            return

        # Disable topological symmetry.  We only activated it to see if it succeeds.
        pm.symmetricModelling(topoSymmetry=False)

    def check_world_space_symmetry(self, shape, vertices, tolerance=0.001):
        """
        Check if a mesh is symmetric around YZ.
        """
        # Find all vertices that are on -X, or on the YZ plane.
        indices = []
        for idx, vert in enumerate(vertices):
            if vert[0] < 0.0001:
                indices.append(idx)

        # Select those vertices with symmetry, so we also select symmetric vertices.
        verts = ['%s.vtx[%i]' % (shape.name(), idx) for idx in indices]

        old_symmetry = pm.symmetricModelling(q=True, symmetry=True)
        old_about = pm.symmetricModelling(q=True, about=True)
        old_axis = pm.symmetricModelling(q=True, axis=True)
        old_tolerance = pm.symmetricModelling(q=True, tolerance=True)
        
        try:
            pm.symmetricModelling(e=True, symmetry=True, about='world', axis='x', tolerance=tolerance)
            pm.select(verts, symmetry=True)

            # Find the indices of any vertices that weren't selected.  This is a bit roundabout
            # since pm.runtime.InvertSelection doesn't work.
            all_indices = set(range(len(vertices)))
            selected_indices = set()
            for sel in pm.ls(sl=True):
                selected_indices |= set(sel.indices())

            deselected_indices = all_indices - selected_indices
            if deselected_indices:
                deselected_verts = ' '.join('%s.vtx[%i]' % (shape.name(), idx) for idx in deselected_indices)
                self.log('Mesh isn\'t world space symmetric (%i unmatched %s)' % (len(deselected_indices), 'vertex' if len(deselected_indices) == 1 else'vertices'),
                        nodes=deselected_verts)
        finally:
            pm.select(deselect=True)
            try:
                pm.symmetricModelling(e=True, symmetry=old_symmetry, about=old_about, axis=old_axis, tolerance=old_tolerance)
            except RuntimeError:
                # Ignore errors if the previous symmetry mode doesn't activate for some reason.
                pass
        
    def check_joint_label_symmetry(self, joints):
        """
        Verify that joints are fully labelled, and that labels are symmetric with no mismatches.
        This is very useful for copying and mirroring skin weights, and we use it for the remaining
        skeleton symmetry checks.

        Labels can normally be duplicated, eg. for multiple finger joints, but that introduces
        heuristics that aren't documented anywhere.  (Does it use distance to match up joints
        if there are multiple matches?)  We ignore that here, and expect that all joint labels
        are completely unique.  If you have multple index finger joints, use an "Other" joint
        type and specify a unique label.

        Any influences in joints that isn't a joint is ignored.

        Return (symmetry, center).  symmetry is a map from left to right joints, and center are
        center joints.  Asymmetric non-center joints that we warn about aren't returned.
        """
        unlabelled_joints = []
        joints_left = {}
        joints_right = {}
        joints_center = {}
        for joint in joints:
            if not isinstance(joint, pm.nodetypes.Joint):
                continue

            joint_type = joint.attr('type').get()
            joint_side = joint.attr('side').get()

            if joint_type == 0:
                # This joint has no type set.
                unlabelled_joints.append(joint)
                continue

            # A joint label can either be set by the type, or if type is "other" (18), set by otherType.
            # If side is Center (0) or None (3), the joint label should be unique.  These are joints that
            # are in the center (eg. spine joints), or which are intentionally asymmetric.  We treat center
            # and none the same.
            # 
            # If side is Left or Right, it should be paired with a mirrored joint with the same label.
            joint_label = joint_type
            if joint_label == 18:
                joint_label = joint.attr('otherType').get()

            # Figure out which category to put this joint.
            category = None
            if joint_side in (0, 3):
                category = joints_center
            elif joint_side == 1:
                category = joints_left
            elif joint_side == 2:
                category = joints_right
            else:
                raise RuntimeError('Unknown joint side on %s: %i' % (joint.nodeName(), joint_side))

            if joint_label in category:
                # This is a duplicate label.
                nodes = [joint, category[joint_label]]

                joint_side_names = {
                    0: 'center',
                    1: 'left side',
                    2: 'right side',
                    3: 'center',
                }

                self.log('Joint label conflicts for %s type %s' % (joint_side_names[joint_side], joint_label), nodes=nodes)
                continue

            category[joint_label] = joint

        # Any joint labels in joints_center shouldn't appear in joints_left or joints_right.
        for joint_label, joint in joints_center.iteritems():
            for category in (joints_left, joints_right):
                conflicting_joint = category.get(joint_label)
                if conflicting_joint:
                    nodes = [joint, conflicting_joint]
                    self.log('Center joint with label %s conflicts with symmetric joint with the same label' % joint_label, nodes=nodes)

        # Map left and right joints together to return.
        # Any joint labels that appear in joints_left should appear in joints_right, and vice versa.
        symmetric_joints = {}
        warned_joints = set()
        joints_with_missing_symmetry = []
        for joint_label in set(joints_left.keys()) | set(joints_right.keys()):
            if joint_label not in joints_left:
                joints_with_missing_symmetry.append(joints_right[joint_label])
            elif joint_label not in joints_right:
                joints_with_missing_symmetry.append(joints_left[joint_label])
            else:
                symmetric_joints[joints_left[joint_label]] = joints_right[joint_label]

        if joints_with_missing_symmetry:
            self.log('Left or right joints without symmetric joints', nodes=joints_with_missing_symmetry)
                
        if unlabelled_joints:
            self.log('Some joints have no joint label', nodes=unlabelled_joints)

        return symmetric_joints, joints_center.values()

    def check_skin_cluster_geom_matrix(self, skin_cluster):
        """
        skinCluster.geomMatrix is the world matrix of the mesh at the time it was bound.  Make sure this matches the
        mesh now.  This normally shouldn't happen unless the mesh transform is unlocked.
        """
        geom_matrix = skin_cluster.attr('geomMatrix').get()
        world_matrix = self.node.attr('worldMatrix[0]').get()
        if not geom_matrix.isEquivalent(world_matrix, 0.0001):
            self.log('geomMatrix of a skinCluster doesn\'t match the mesh transform', nodes=[skin_cluster])

    def check_skin_cluster_in_bind_pose(self, skin_cluster):
        """
        Each influence on a skinCluster stores the transform it had at bind time.  When we're
        in bind pose, this should match the position of the influence, giving no transform.  Verify
        this.
        """
        influences = pm.skinCluster(skin_cluster, q=True, influence=True)
        joints_not_in_bind_pose = []
        bind_pre_matrix_array = skin_cluster.attr('bindPreMatrix')
        for influence_connection in skin_cluster.attr('matrix'):
            idx = influence_connection.index()

            # Find the corresponding influence.
            joints = pm.listConnections(influence_connection, s=True, d=False)
            if not joints:
                continue
            assert len(joints) == 1
            joint = joints[0]

            world_inverse_matrix = joint.attr('worldInverseMatrix').get()
            bind_matrix_value = bind_pre_matrix_array.elementByLogicalIndex(idx).get()
            if not world_inverse_matrix.isEquivalent(bind_matrix_value, 0.001):
                joints_not_in_bind_pose.append(joint)

        if joints_not_in_bind_pose:
            self.log('Some influences aren\'t in bind pose', nodes=joints_not_in_bind_pose)

    def check_skin_cluster_max_influences(self, skin_cluster, max_influences):
        if max_influences == 0:
            return

        unweighted_vertices = set()
        excessively_weighted_vertices = {}
        for vtx, weights in enumerate(skin_cluster.weightList):
            # Use cmds instead of pm here for speed.
            influences = cmds.getAttr('%s.weights' % weights, mi=True) or []
            cnt = len(influences)
#            cnt = len(weights.weights.get(mi=True))
            if cnt == 0:
                unweighted_vertices.add(vtx)
            elif cnt > max_influences:
                excessively_weighted_vertices[vtx] = cnt

        if unweighted_vertices:
            vertices = str(self.node.getShape())
            verts = ' '.join('%s.vtx[%i]' % (vertices, idx) for idx in unweighted_vertices)
            self.log('%i %s aren\'t weighted to any influences' % (
                len(unweighted_vertices),
                'vertices' if len(unweighted_vertices) != 1 else 'vertex'),
                nodes=verts)

        if excessively_weighted_vertices:
            # Avoid using PyMel's .vtx access here, since it's slow.
            vertices = str(self.node.getShape())
            verts = ' '.join('%s.vtx[%i]' % (vertices, idx) for idx in excessively_weighted_vertices.keys())
            self.log('%i %s are weighted to more than %i %s' % (
                len(excessively_weighted_vertices),
                'vertices' if len(excessively_weighted_vertices) != 1 else 'vertex',
                max_influences,
                'influence' if max_influences == 1 else 'influences'),
                nodes=verts)
        
    def check_skeleton(self):
        shapes = self.node.getShapes()
        base_mesh = shapes[-1]
        skin_clusters = pm.listFuture(base_mesh, type='skinCluster')

        if len(skin_clusters) > 1:
            self.log('Mesh has more than one skinCluster', nodes=skin_clusters)
        if not skin_clusters:
            return

        skin_cluster = skin_clusters[0]

        self.check_skin_cluster_geom_matrix(skin_cluster)
        self.check_skin_cluster_in_bind_pose(skin_cluster)

        self.progress.set_task_progress('Checking max influences', percent=0.4, force=True)
        self.check_skin_cluster_max_influences(skin_cluster, self.config['max_influences'])

        self.progress.set_task_progress('Checking skeleton', percent=0.6, force=True)
        influences = pm.skinCluster(skin_cluster, q=True, influence=True)

        # We expect to have stub joints that aren't bound to the skeleton.  These should still be
        # symmetric and have correct labelling.  Search influences for a single child that isn't in
        # the influence list and add them.
        #
        # This is a bit fuzzy, since we can pick up unrelated things.  For example, the head joint
        # might have the root of a hair skeleton underneath it.
        stub_joints = []
        for influence in influences:
            # Only look at joints that have a single child.
            children = pm.listRelatives(influence, children=True, type='joint')
            if len(children) != 1:
                continue

            possible_stub_joint = children[0]
            if possible_stub_joint in influences:
                continue

            # If this joint has influences, it's part of a different skinCluster, so don't add it
            # as a stub joint.
            if pm.listConnections(possible_stub_joint.attr('worldMatrix[0]'), s=False, d=True, type='skinCluster'):
                continue

            # If this joint has any children, don't treat it as a stub joint.
            if len(pm.listRelatives(possible_stub_joint)) > 0:
                continue

            stub_joints.append(possible_stub_joint)

        # log.debug('Found stub joints: %s', ', '.join(joint.nodeName() for joint in stub_joints))
        influences.extend(stub_joints)

        # Stub joints should have a zero jointOrient.  This is set to something random by orient joints,
        # and causes the stub joint to point out in an odd direction.
        for joint in stub_joints:
            rot = joint.attr('jointOrient').get()
            if om.MVector(rot).length() > 0.001:
                self.log('Stub joint %s has a nonzero joint orient' % joint.nodeName(), nodes=[joint])

        symmetric_joints, joints_center = self.check_joint_label_symmetry(influences)

        # All joints should have zero rotations when in bind pose.
        joints_with_nonzero_rotations = []
        for influence in influences:
            # Treat rotations that are equivalent to zero as being zero.  This prevents warnings
            # when joints have rotations like (0,360,0), which happens a lot when constraints or
            # IK control the joint.
            quat = om.MQuaternion()
            om.MFnTransform(influence.__apimobject__()).getRotation(quat)
            if not quat.isEquivalent(om.MQuaternion.identity, 0.001):
                joints_with_nonzero_rotations.append(influence)

        if joints_with_nonzero_rotations:
            self.log('%i %s nonzero rotations' % (
                len(joints_with_nonzero_rotations), 
                'joint has' if len(joints_with_nonzero_rotations) == 1 else 'joints have'
                ), nodes=joints_with_nonzero_rotations)

        # If a joint is a stub joint, its mirrored joint should also be a stub joint.  It's easy to
        # accidentally leave some of these bounds, which can cause hard to debug "not all influences
        # could be matched" warnings when mirroring skin weights.
        for left_joint, right_joint in symmetric_joints.iteritems():
            if left_joint in stub_joints and right_joint not in stub_joints:
                self.log('Left joint %s is a stub joint, but right joint %s is bound' % (left_joint.nodeName(), right_joint.nodeName()), nodes=[left_joint, right_joint])
            if right_joint in stub_joints and left_joint not in stub_joints:
                self.log('Right joint %s is a stub joint, but left joint %s is bound' % (right_joint.nodeName(), left_joint.nodeName()), nodes=[right_joint, left_joint])

        # All center joints should have an X value of 0.
        for joint in joints_center:
            pos = pm.xform(joint, q=True, ws=True, t=True)
            if abs(pos[0]) > self.config['error_threshold']:
                self.log('Center joint %s is not aligned to the YZ plane: %f' % (joint.nodeName(), pos[0]), nodes=[joint])

        for left_joint, right_joint in symmetric_joints.iteritems():
            # Symmetric joints should be in symmetric positions across the YZ plane.
            left_pos = pm.xform(left_joint, q=True, ws=True, t=True)
            right_pos = pm.xform(right_joint, q=True, ws=True, t=True)

            max_error_threshold = max(abs(left_pos[0] + right_pos[0]),
                                      abs(left_pos[1] - right_pos[1]),
                                      abs(left_pos[2] - right_pos[2]))
            if max_error_threshold > self.config['error_threshold']:
                self.log('Joint positions aren\'t symmetric: %s, %s (error: %f)' % (left_joint.nodeName(), right_joint.nodeName(), max_error_threshold),
                        nodes=[left_joint, right_joint])

            # Symmetric joints should have the same rotateOrder.
            left_rotate_order = left_joint.attr('rotateOrder').get()
            right_rotate_order = right_joint.attr('rotateOrder').get()
            if left_rotate_order != right_rotate_order:
                self.log('Symmetric joints have different rotateOrders: %s, %s' % (left_joint.nodeName(), right_joint.nodeName()), nodes=[left_joint,right_joint])

            left_rot = om.MVector(*pm.xform(left_joint, q=True, ws=True, ro=True)) / 180 * math.pi
            right_rot = om.MVector(*pm.xform(right_joint, q=True, ws=True, ro=True)) / 180 * math.pi
            left_rot = om.MEulerRotation(left_rot[0], left_rot[1], left_rot[2], left_rotate_order)
            right_rot = om.MEulerRotation(right_rot[0], right_rot[1], right_rot[2], right_rotate_order)

            rotations = [
                (0,0,0),
                (90,0,0),
                (90,0,0),
            ]

            def get_axis_angle(quat):
                axis = om.MVector()

                angle = om.MScriptUtil()
                angle.createFromDouble(0)
                angle_ptr = angle.asDoublePtr()

                angle_ptr = angle.asDoublePtr()
                quat.getAxisAngle(axis, angle_ptr)

                return axis, angle.getDoubleArrayItem(angle_ptr, 0)
                
            x_vector = om.MVector(1,0,0)
            y_vector = om.MVector(0,1,0)
            z_vector = om.MVector(0,0,1)

            left_x_vector = x_vector * left_rot.asMatrix()
            right_x_vector = x_vector * right_rot.asMatrix()
            left_y_vector = y_vector * left_rot.asMatrix()
            right_y_vector = y_vector * right_rot.asMatrix()
            left_z_vector = z_vector * left_rot.asMatrix()
            right_z_vector = z_vector * right_rot.asMatrix()

            def check(vector):
                left_vector = vector * left_rot.asMatrix()
                right_vector = vector * right_rot.asMatrix()

                left_angle = left_vector * x_vector
                right_angle = right_vector * x_vector
                return abs(left_angle - right_angle) < 0.001 or abs(left_angle + right_angle) < 0.001

            if not check(om.MVector(1,0,0)) or not check(om.MVector(0,1,0)) or not check(om.MVector(0,0,1)):
                self.log('Symmetric joints %s and %s don\'t have symmetric rotations' %
                        (left_joint.nodeName(), right_joint.nodeName()),
                        nodes=[left_joint, right_joint])

    def run(self):
        if not isinstance(self.node, pm.nodetypes.Transform):
            self.log('Skipped node %s (not a transform)' % self.node.nodeName(), nodes=[self.node])
            return self.warnings

        shapes = self.node.getShapes()
        if len(shapes) < 1:
            self.log('Skipped node %s (not a shape)' % self.node.nodeName(), nodes=[self.node])
            return self.warnings

        self.log('Mesh: %s' % self.node.nodeName(), nodes=[self.node])
        self.log('')

        # Check for bad geometry.
        self.progress.set_task_progress('Checking geometry', percent=0, force=True)

        nonmanifold_verts = pm.ls(pm.polyInfo(self.node, nonManifoldVertices=True))
        nonmanifold_verts_count = sum(len(vtx) for vtx in nonmanifold_verts)
        if nonmanifold_verts_count:
            self.log('Mesh has %i nonmanifold %s' %
                (nonmanifold_verts_count, 'vertices' if nonmanifold_verts_count != 1 else 'vertex'),
                nodes=nonmanifold_verts)

        nonmanifold_edges = pm.ls(pm.polyInfo(self.node, nonManifoldEdges=True))
        nonmanifold_edges_count = sum(len(vtx) for vtx in nonmanifold_edges)
        if nonmanifold_edges_count:
            self.log('Mesh has %i nonmanifold %s' %
                (nonmanifold_edges_count, 'edges' if nonmanifold_edges_count != 1 else 'edge'),
                nodes=nonmanifold_edges)

        lamina_faces = pm.ls(pm.polyInfo(self.node, laminaFaces=True))
        lamina_face_count = sum(len(vtx) for vtx in lamina_faces)
        if lamina_face_count:
            self.log('Mesh has %i lamina %s' %
                (lamina_face_count, 'faces' if lamina_face_count != 1 else 'face'),
                nodes=lamina_faces)

        # Degenerate faces
        min_face_area = 0.0001
        pm.select(self.node)
        pm.polySelectConstraint(mode=3, type=constraint_face, geometricarea=True, geometricareabound=(0, min_face_area))
        degenerate_faces = pm.ls(sl=True)
        pm.polySelectConstraint(mode=0, type=constraint_face, geometricarea=False)
        degenerate_face_count = sum(len(vtx) for vtx in degenerate_faces)
        if degenerate_face_count:
            self.log('Mesh has %i degenerate %s.' %
                (degenerate_face_count, 'faces' if degenerate_face_count != 1 else 'face'),
                nodes=degenerate_faces)

        # Degenerate UV faces.  Degenerate UV edges would be useful too, but there's no selection constraint
        # for that.
        min_uv_area = 0.0000001
        pm.select(self.node)
        pm.polySelectConstraint(mode=3, type=constraint_uv, texturedarea=True, texturedareabound=(0, min_uv_area))
        degenerate_uvs = pm.ls(sl=True)
        pm.polySelectConstraint(mode=0, type=constraint_uv, texturedarea=False)
        degenerate_uv_count = sum(len(vtx) for vtx in degenerate_uvs)
        if degenerate_uv_count:
            self.log('Mesh has %i degenerate %s.' %
                (degenerate_uv_count, 'UVs' if degenerate_uv_count != 1 else 'UV'),
                nodes=degenerate_uvs)

        # Degenerate edges
        min_edge_length = 0.0001
        pm.select(self.node)
        pm.polySelectConstraint(mode=3, type=constraint_edge, length=True, lengthbound=(0, min_edge_length))
        degenerate_edges = pm.ls(sl=True)
        pm.polySelectConstraint(mode=0, type=constraint_edge, length=False)
        degenerate_edge_count = sum(len(vtx) for vtx in degenerate_edges)
        if degenerate_edge_count:
            self.log('Mesh has %i degenerate %s.' %
                (degenerate_edge_count, 'edges' if degenerate_edge_count != 1 else 'edge'),
                nodes=degenerate_edges)

        # Ngons
        pm.select(self.node)
        pm.polySelectConstraint(mode=3, type=constraint_face, size=3)
        ngons = pm.ls(sl=True)
        pm.polySelectConstraint(mode=0, type=constraint_face, size=3)
        ngon_count = sum(len(vtx) for vtx in ngons)
        if ngon_count:
            self.log('Mesh has %i %s.' %
                (ngon_count, 'ngons' if ngon_count != 1 else 'ngon'),
                nodes=ngons)

        self.progress.set_task_progress('Checking history', percent=0.1, force=True)

        self.check_history()
        self.check_tweak_node()
        self.check_vertex_tweaks(True)
        self.check_vertex_tweaks(False)

        self.progress.set_task_progress('Checking overlapping vertices', percent=0.15, force=True)
        self.check_overlapping_vertices()

        self.progress.set_task_progress('Checking skeleton', percent=0.2, force=True)
        self.check_skeleton()

        # If a mesh has more than two shapes, there may be unwanted construction history left on it.
        if len(shapes) > 2:
            self.log('Mesh has more than two shapes in its history', nodes=[self.node])

        output = shapes[0]
        output_points = get_vertices(output)

        if len(shapes) >= 2:
            base = shapes[-1]
            base_points = get_vertices(base)
            self.check_identical_to_orig(base_points, output_points)

            # Do all future mesh checks against the base mesh.
    #        output = base
    #        output_points = base_points

        self.check_uv_sets(output)

        # Check that the base mesh is symmetric in world space.  Note that this won't work if we give it the
        # base mesh, since polyListComponentConversion doesn't work on intermediate meshes for some reason.
        self.progress.set_task_progress('Checking topological symmetry', percent=0.4, force=True)
        self.check_topological_symmetry(output, output_points)

        self.progress.set_task_progress('Checking world space symmetry', percent=0.6, force=True)
        self.check_world_space_symmetry(output, output_points, self.config['vertex_error_threshold'])

        if not self.warnings:
            self.log('%s: OK' % self.node.nodeName(), nodes=[self.node])

        return self.warnings

    def check_uv_sets(self, shape):
        # Check for UV sets with no name set.  These are usually caused by buggy Maya modelling
        # operations.  They don't appear anywhere in the UI, but they trigger "invalid or unused
        # components" warnings on load that don't tell you what the problem is.
        for uv_set in shape.uvst:
            if uv_set.uvSetName.get() is None:
                self.log('UV set %i has no name' % uv_set.index(), nodes=[shape])
    
class UI(maya_helpers.OptionsBox):
    title = 'Validate Character'

    def __init__(self):
        super(UI, self).__init__()

    def options_box_setup(self):
        self.optvars.add('zValidateCharacterMaxInfluences', 'int', 4)
        self.optvars.add('zValidateCharacterErrorThreshold', 'float', 0.001)
        self.optvars.add('zValidateCharacterErrorVertexThreshold', 'float', 0.001)
        self.optvars.add('zValidateCharacterOverlappingVertexThreshold', 'float', 0.001)

        self.option_box = pm.columnLayout(adjustableColumn=1)
        parent = self.option_box

#        pm.optionMenuGrp('cpwInputShapeList', label='Shape:')
#        pm.optionMenuGrp('cpwInputBlendShapeTargets', label='Blend shape target:', cc=lambda unused: input_blend_shape_changed())

        pm.intSliderGrp('valMaxInfluences', label='Max joint influences', field=True, min=0, max=10)
        pm.floatSliderGrp('valJointErrorThreshold', label='Symmetry error threshold (joints)', field=True, fieldMinValue=0.00001, fieldMaxValue=10, min=0, max=0.1)
        pm.floatSliderGrp('valVertexErrorThreshold', label='Symmetry error threshold (vertices)', field=True, fieldMinValue=0.00001, fieldMaxValue=10, min=0, max=0.1)
        pm.floatSliderGrp('valOverlappingVertexThreshold', label='Overlapping vertex threshold', field=True, fieldMinValue=0.00001, fieldMaxValue=10, min=0, max=0.1)

    def option_box_save(self):
        self.optvars['zValidateCharacterMaxInfluences'] = pm.intSliderGrp('valMaxInfluences', q=True, v=True)
        self.optvars['zValidateCharacterErrorThreshold'] = pm.floatSliderGrp('valJointErrorThreshold', q=True, v=True)
        self.optvars['zValidateCharacterErrorVertexThreshold'] = pm.floatSliderGrp('valVertexErrorThreshold', q=True, v=True)
        self.optvars['zValidateCharacterOverlappingVertexThreshold'] = pm.floatSliderGrp('valOverlappingVertexThreshold', q=True, v=True)

    def option_box_load(self):
        pm.intSliderGrp('valMaxInfluences', edit=True, v=self.optvars['zValidateCharacterMaxInfluences'])
        pm.floatSliderGrp('valJointErrorThreshold', edit=True, v=self.optvars['zValidateCharacterErrorThreshold'])
        pm.floatSliderGrp('valVertexErrorThreshold', edit=True, v=self.optvars['zValidateCharacterErrorVertexThreshold'])
        pm.floatSliderGrp('valOverlappingVertexThreshold', edit=True, v=self.optvars['zValidateCharacterOverlappingVertexThreshold'])
        
    def option_box_apply(self):
        pm.setParent(self.option_box)

        config = {
            'max_influences': pm.intSliderGrp('valMaxInfluences', q=True, v=True),
            'error_threshold': pm.floatSliderGrp('valJointErrorThreshold', q=True, v=True),
            'vertex_error_threshold': pm.floatSliderGrp('valVertexErrorThreshold', q=True, v=True),
            'vertex_overlap_threshold': pm.floatSliderGrp('valOverlappingVertexThreshold', q=True, v=True),
        }

        selection = pm.ls(sl=True)

        # Convert the selection to transforms, so we work even if components are selected.
        nodes = []
        for obj in selection:
            if isinstance(obj, pm.general.Component):
                node = obj.node().getTransform()
            elif isinstance(obj, pm.nodetypes.Transform):
                node = obj
            elif isinstance(obj, pm.nodetypes.Mesh):
                node = obj.getTransform()
            else:
                log.info('Can\'t check %s (not a mesh)', str(obj))
                continue

            # In case multiple vertices are selected, don't add the same transform more than
            # once.  We use a simple search for this rather than converting to a set, since
            # we won't have enough entries in nodes for it to matter, and this preserves the
            # order of the selection.
            if node not in nodes:
                nodes.append(node)

        if not nodes:
            log.warning('Select one or more meshes to validate')
            return
        
        all_results = []
        with maya_helpers.ProgressWindowMaya(len(nodes), title='Validating Character',
                with_titles=True, with_secondary_progress=True, with_cancel=True) as progress:
            for node in nodes:
                progress.update(text='Validating mesh: %s' % node.nodeName())
                validator = Validate(config, node, progress)
                warnings = validator.run()
                all_results.append((node, warnings))

        idx_to_node = {}
        def select_nodes():
            selected_idx = pm.textScrollList(results, q=True, selectIndexedItem=True)
            if not selected_idx:
                return

            selected_idx = selected_idx[0]
            selected_warning = idx_to_node.get(selected_idx)
            if selected_warning is None:
                return

            if selected_warning['nodes']:
                # This can be slow if we use pm.select with a large vertex list, so we use
                # MEL here.
                pm.mel.eval('select %s' % selected_warning['nodes'])
                pm.viewFit()

        # Show results.
        pm.window(width=800, height=400,
                title='Mesh Validation Results')
        pm.paneLayout()

        results = pm.textScrollList(selectCommand=select_nodes)

        first = True
        for node, warnings in all_results:
            if not first:
                pm.textScrollList(results, edit=True, append='')
            first = False

            for warning in warnings:
                pm.textScrollList(results, edit=True, append=warning['msg'])
                idx = pm.textScrollList(results, q=True, numberOfItems=True)
                idx_to_node[idx] = warning

        pm.showWindow()

        pm.select(nodes)

