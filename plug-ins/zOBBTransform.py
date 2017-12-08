import itertools, sys
from pprint import pformat
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import math, traceback, time

from obb_transform import obb_transform
from zMayaTools import maya_logging

log = maya_logging.get_log()

_rotation_modes = [
    'none',
    'full',
    'primary',
    'secondary',
]

def iterate_array_handle(array):
    """
    Mostly fix MArrayDataHandle array iteration.
    """
    while True:
        # Call elementIndex() to see if there are any values at all.  It'll throw RuntimeError
        # if there aren't.
        try:
            array.elementIndex()
        except RuntimeError as e:
            # We've advanced beyond the end of the array.
            break

        yield array.inputValue()

        try:
            array.next()
        except RuntimeError as e:
            break

def get_matrix3(v):
    # The docs all say you can construct an MMatrix by passing in a list of values, but that
    # doesn't actually work.
    result = om.MMatrix()
    mat = [
        v[0][0], v[0][1], v[0][2], 0,
        v[1][0], v[1][1], v[1][2], 0,
        v[2][0], v[2][1], v[2][2], 0,
        0, 0, 0, 1,
    ]
    om.MScriptUtil.createMatrixFromList(mat, result)
    return result

def setScale(transform, scale, space):
    scale_array = om.MScriptUtil()
    scale_array.createFromDouble(scale.x, scale.y, scale.z)
    transform.setScale(scale_array.asDoublePtr(), space)

# Really?
def callDouble4(func):
    scale_array = om.MScriptUtil()
    scale_array.createFromDouble(0, 0, 0, 0)
    ptr = scale_array.asDoublePtr()
    func(ptr)

    x = om.MScriptUtil.getDoubleArrayItem(ptr, 0)
    y = om.MScriptUtil.getDoubleArrayItem(ptr, 1)
    z = om.MScriptUtil.getDoubleArrayItem(ptr, 2)
    scale = om.MVector(x, y, z)
    return scale

def getScale(transform, space):
    def func(ptr):
        transform.getScale(ptr, space)

    return callDouble4(func)

def set_double3(attr, value):
    attr.set3Double(value.x, value.y, value.z)
    attr.setClean()

def fv(v):
    return '(%.3f %.3f %.3f)' % (v.x, v.y, v.z)

class zOBBTransform(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x124745)

    def __init__(self, *args, **kwargs):
        super(zOBBTransform, self).__init__(*args, **kwargs)

    @classmethod
    def get_mesh_info(cls, dataBlock, meshAttr, groupIdAttr):
        inputMeshHandle = dataBlock.inputValue(meshAttr)
        if inputMeshHandle is None:
            return None

        groupId = dataBlock.inputValue(groupIdAttr).asLong()

        try:
            it = om.MItGeometry(inputMeshHandle, groupId, True)
        except RuntimeError:
            # This throws an "Argument is a NULL pointer" error if the mesh isn't connected.  How
            # can we check this?
            return None

        points = om.MPointArray()
        it.allPositions(points, om.MSpace.kWorld)

        point_list = []
        for idx in xrange(points.length()):
            point = points[idx]
            point_list.append((point.x, point.y, point.z))

        forward, up, right, center, ext = obb_transform.obb_transform(point_list)

        right = om.MVector(*right)
        up = om.MVector(*up)
        forward = om.MVector(*forward)
        center = om.MVector(*center)
        ext = om.MVector(*ext)

        # XXX: The rest of this is currently the main bottleneck and should be moved to native.

        # Make a list of the number of vertices down each positive and negative axis, so we can
        # match up the two meshes.
        mvector_list = []
        for idx in xrange(points.length()):
            point = points[idx]

            # Center vertices around their center, so translations don't throw off axis matching.
            # Using -= here will crash Maya for some reason.
            point = point - center
            mvector_list.append(om.MVector(point.x, point.y, point.z))

        axis_vertices = []

        for axis in (right, up, forward):
            # Align each axis to the X axis, and make a list of vertex indices that are +X and -X.
            # This assumes that most deformations don't flip a mesh inside out or change the mesh
            # excessively.
            quat = axis.rotateTo(om.MVector(1,0,0))

            positive_indices = set()
            negative_indices = set()
            for idx, point in enumerate(mvector_list):
                point = point.rotateBy(quat)

                f = point[0]
                if f >= 0:
                    positive_indices.add(idx)
                else:
                    negative_indices.add(idx)
            
            axis_vertices.append((positive_indices, negative_indices))

#        sys.__stdout__.write('%f %f %f %f %f\n' %(d1*1000, d2*1000, d3*1000, d4*1000, d5*1000))

        return axis_vertices, (right, up, forward), center, ext

    def compute(self, plug, dataBlock):
        if plug == zOBBTransform.updateOrigAttr:
            self.orig_mesh_info = self.get_mesh_info(dataBlock, self.origMeshAttr, self.origMeshGroupIdAttr)
            dataBlock.setClean(plug)
            return

        if plug == zOBBTransform.updateCurrentAttr:
            self.current_mesh_info = self.get_mesh_info(dataBlock, self.currentMeshAttr, self.currentMeshGroupIdAttr)
            if self.current_mesh_info is not None:
                axis_vertices, (right, up, forward), center, ext = self.current_mesh_info
            
            dataBlock.setClean(plug)
            return

        if plug == zOBBTransform.outPivotAttr:
            dataBlock.inputValue(self.updateOrigAttr)
            if self.orig_mesh_info is not None:
                src_axis_vertices, src_vectors, src_center, src_extents = self.orig_mesh_info
                set_double3(dataBlock.outputValue(self.outPivotAttr), src_center)
            dataBlock.setClean(plug)
            return

        if plug in self.output_attrs or (plug.isChild() and plug.parent() in self.output_attrs):
            # Update the input meshes.  The orig mesh is usually static, so that one will usually
            # already be clean.
            dataBlock.inputValue(self.updateOrigAttr)
            dataBlock.inputValue(self.updateCurrentAttr)

            # Read the rotation mode and scale weight inputs.
            rotation_mode_idx = dataBlock.inputValue(zOBBTransform.rotationModeAttr).asInt()
            rotation_mode = _rotation_modes[rotation_mode_idx]

            scale_weights = []
            for attr in zOBBTransform.scaleWeightAttrs:
                weights = dataBlock.inputValue(attr).asDouble3()
                scale_weights.append(weights)

            translate, rotate, scale = self.get_relative_transform(rotation_mode, scale_weights)

            set_double3(dataBlock.outputValue(self.outTranslateAttr), translate)
            set_double3(dataBlock.outputValue(self.outRotateAttr), rotate)
            set_double3(dataBlock.outputValue(self.outScaleAttr), scale)

#            sys.__stdout__.write('%f %f\n' %(d1*1000, d2*1000))
#            sys.__stdout__.flush()

            dataBlock.setClean(plug)

            return

        return super(zOBBTransform, self).compute(plug, dataBlock)

    @classmethod
    def get_quaternion_from_vectors(cls, src_vector, dst_vector, rotation_mode='full'):
        assert rotation_mode in ('full', 'primary', 'secondary', 'none')
        if rotation_mode == 'none':
            return om.MQuaternion()

        # Make a copy, so we don't modify the caller's list.
        src_vector = list(src_vector)

        #src_vector = [v.normal() for v in src_vector]
        #dst_vector = [v.normal() for v in dst_vector]

        primary_rotation = src_vector[0].rotateTo(dst_vector[0])
        if rotation_mode == 'primary':
            return primary_rotation

        src_vector[1] = src_vector[1].rotateBy(primary_rotation)
        secondary_rotation = src_vector[1].rotateTo(dst_vector[1])
        if rotation_mode == 'secondary':
            return secondary_rotation

        return primary_rotation * secondary_rotation

    def get_relative_transform(self, rotation_mode, scale_weights):
        assert len(scale_weights) == 3
        scale_weights = [om.MVector(*w) for w in scale_weights]

        if self.orig_mesh_info is None or self.current_mesh_info is None:
            return om.MVector(0,0,0), om.MVector(0,0,0), om.MVector(1,1,1)

        src_axis_vertices, src_vectors, src_center, src_extents = self.orig_mesh_info
        dst_axis_vertices, dst_vectors, dst_center, dst_extents = self.current_mesh_info

#        return src_vectors, dst_vectors, dst_center - src_center, om.MVector(1,1,2)
#        scale = om.MVector(dst_extents.x / src_extents.x, dst_extents.y / src_extents.y, dst_extents.z / src_extents.z)

#    #    print '----- axis0:', fv(src_vectors[0]), fv(src_vectors[1]), fv(src_vectors[2])
#    #    print '----- axis1:', fv(dst_vectors[0]), fv(dst_vectors[1]), fv(dst_vectors[2])

        # We have oriented vectors for both meshes, but the vectors might be pointing in different
        # directions.  We need to map them to each other.   src_axis_vertices[0][0] is the number of
        # vertices on the positive X axis, src_axis_vertices[0][1] on the negative X axis, and so
        # on.  

        axes_matched = {}

        for dst_axis in xrange(3):
            # Find the source axis with the most matching vertices to this destination axis, and
            # whether the axis is reversed or not.
            for src_axis in xrange(3):
                src_vertices_positive = src_axis_vertices[src_axis][False]
                dst_vertices_positive = dst_axis_vertices[dst_axis][False]
                src_vertices_negative = src_axis_vertices[src_axis][True]
                dst_vertices_negative = dst_axis_vertices[dst_axis][True]

                matching_vertices = len(dst_vertices_positive & src_vertices_positive) + len(dst_vertices_negative & src_vertices_negative)
                matching_vertices_flipped = len(dst_vertices_positive & src_vertices_negative) + len(dst_vertices_negative & src_vertices_positive)

                # If flipped is a closer match than not flipped, we only need to store flipped.
                if matching_vertices > matching_vertices_flipped:
                    axes_matched[(src_axis, dst_axis)] = (matching_vertices, False)
                else:
                    axes_matched[(src_axis, dst_axis)] = (matching_vertices_flipped, True)

        # Check all permutations of axes to find the closest match.
        best_permutation = 0
        best_permutation_count = 0
        src_to_dst_axes = {}
        for order in itertools.permutations([0,1,2]):
            # Count the total number of matching vertices in this permutation.
            total_matched = 0
            for axis in xrange(3):
                src_axis = axis
                dst_axis = order[axis]
                total_matched += axes_matched[(src_axis, dst_axis)][0]

            if total_matched >= best_permutation_count:
                best_permutation_count = total_matched
                best_permutation = order

                for axis in xrange(3):
                    src_axis = axis
                    dst_axis = order[axis]
                    negative = axes_matched[(src_axis, dst_axis)][1]
                    src_to_dst_axes[src_axis] = (dst_axis, negative)

        # Reorder the destination vectors to match the source vectors, and flip any that are pointing
        # in the wrong direction.  Reorder the extents too (these are always positive and we don't need
        # to flip them).
        reordered_dst_vectors = []
        reordered_dst_extents = [0,0,0]
        for src_axis in xrange(3):
            dst_axis, negative = src_to_dst_axes[src_axis]

            dst_vector = dst_vectors[dst_axis]
            if negative:
                dst_vector = dst_vector * -1
            reordered_dst_vectors.append(dst_vector)
            reordered_dst_extents[src_axis] = dst_extents[dst_axis]

        dst_vectors = reordered_dst_vectors
        dst_extents = om.MVector(*reordered_dst_extents)

        transform = om.MMatrix()

        # The extents are in OBB space.  Rotate from world space to OBB space to apply them as scale.
        quat = self.get_quaternion_from_vectors(src_vectors, (om.MVector(+1,0,0), om.MVector(0,+1,0)))
        transform *= quat.asMatrix()

        temp = om.MTransformationMatrix()

        # Get the scale of the output relative to the input.  If an extent is zero, there's no
        # scale and just set the relative scale to 1.  For example, if we only have one input
        # vertex, there's no scaling and we'll just report 1,1,1.
        def safe_divide(x, y):
            return 1 if y == 0 else x / y
        dst_scale = om.MVector(safe_divide(dst_extents.x, src_extents.x), safe_divide(dst_extents.y, src_extents.y), safe_divide(dst_extents.z, src_extents.z))

        # Blend the scale according to the weights.  Each input scale axis can affect each output
        # scale axis.  If the weights are the default of (1,0,0), (0,1,0), (0,0,1), then we just
        # use the primary scale for the primary axis, and so on.  If a weight is (0.5, 0.5, 0) then
        # we'll average the primary and secondary axes.  For (0,0,0) we won't use the output scale
        # at all and we'll always be 1.
        scale = [0,0,0]
        for idx in xrange(3):
            weight = scale_weights[idx]
            if weight.x == 0 and weight.y == 0 and weight.z == 0:
                scale[idx] = 1
                continue

            value = 0
            total_weight = 0
            for input_idx in xrange(3):
                t = weight[input_idx]
                total_weight += t
                value += dst_scale[input_idx]*weight[input_idx]

            # Add any remaining weight, so we interpolate to 1.  If the input weights sum to 0.4,
            # then we add 0.6 to make up the rest.
            value += (1-total_weight)

            scale[idx] = value

        scale = om.MVector(*scale)

        setScale(temp, scale, om.MSpace.kPreTransform)
        transform = transform * temp.asMatrix()

        # Rotate back out of OBB space to world space.
        transform *= quat.inverse().asMatrix()

        # Rotate around the center point.
        quat = self.get_quaternion_from_vectors(src_vectors, dst_vectors, rotation_mode)
        transform *= quat.asMatrix()

        # Transform from the source center to the origin to apply rotations and scale.
        temp = om.MTransformationMatrix()
        temp.addTranslation(src_center * -1, om.MSpace.kPostTransform)
        transform = transform * temp.asMatrix()

        temp = om.MTransformationMatrix()
        temp.addTranslation(dst_center, om.MSpace.kPostTransform)
        transform = transform * temp.asMatrix()

        final_transform = om.MTransformationMatrix(transform)
        translate = final_transform.getTranslation(om.MSpace.kTransform)
        rotate = final_transform.rotation().asEulerRotation().asVector()
        scale = getScale(final_transform, om.MSpace.kTransform)

        return translate, rotate, scale

def creator():
    return OpenMayaMPx.asMPxPtr(zOBBTransform())

def initialize():
    mAttr = om.MFnMatrixAttribute()
    tAttr = om.MFnTypedAttribute()
    nAttr = om.MFnNumericAttribute()
    cmpAttr = om.MFnCompoundAttribute()
    uAttr = om.MFnUnitAttribute()
    enumAttr = om.MFnEnumAttribute()

    zOBBTransform.output_attrs = []

    def create_numeric_attr(ln, sn, attrType=om.MFnNumericData.kDouble, niceName=None, writable=True, storable=True,
            default=None, minValue=None, maxValue=None, category='output'):
        if attrType in (om.MFnUnitAttribute.kDistance, om.MFnUnitAttribute.kAngle):
            creator = uAttr
        else:
            creator = nAttr

        attr = creator.create(ln, sn, attrType)
        creator.setWritable(writable)
        creator.setStorable(storable)
        if default is not None:
            creator.setDefault(default)
        if minValue is not None:
            creator.setMin(minValue)
        if maxValue is not None:
            creator.setMax(maxValue)
        if niceName is not None:
            creator.setNiceNameOverride(niceName)
        if category == 'output':
            zOBBTransform.output_attrs.append(attr)
        elif category == 'input':
            input_attrs.append(attr)
        return attr

        
    tx = create_numeric_attr('translateX', 'tx', om.MFnUnitAttribute.kDistance, niceName='Translate X', writable=False, storable=False)
    ty = create_numeric_attr('translateY', 'ty', om.MFnUnitAttribute.kDistance, niceName='Translate Y', writable=False, storable=False)
    tz = create_numeric_attr('translateZ', 'tz', om.MFnUnitAttribute.kDistance, niceName='Translate Z', writable=False, storable=False)

    zOBBTransform.outTranslateAttr = nAttr.create('translate', 't', tx, ty, tz)
    nAttr.setWritable(False)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.outTranslateAttr)
    zOBBTransform.output_attrs.append(zOBBTransform.outTranslateAttr)

    rx = create_numeric_attr('rotateX', 'rx', om.MFnUnitAttribute.kAngle, niceName='Rotate X', writable=False, storable=False)
    ry = create_numeric_attr('rotateY', 'ry', om.MFnUnitAttribute.kAngle, niceName='Rotate Y', writable=False, storable=False)
    rz = create_numeric_attr('rotateZ', 'rz', om.MFnUnitAttribute.kAngle, niceName='Rotate Z', writable=False, storable=False)

    zOBBTransform.outRotateAttr = nAttr.create('rotate', 'r', rx, ry, rz)
    nAttr.setWritable(False)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.outRotateAttr)
    zOBBTransform.output_attrs.append(zOBBTransform.outRotateAttr)

    sx = create_numeric_attr('scaleX', 'sx', om.MFnNumericData.kDouble, niceName='Scale X', writable=False, storable=False)
    sy = create_numeric_attr('scaleY', 'sy', om.MFnNumericData.kDouble, niceName='Scale Y', writable=False, storable=False)
    sz = create_numeric_attr('scaleZ', 'sz', om.MFnNumericData.kDouble, niceName='Scale Z', writable=False, storable=False)

    zOBBTransform.outScaleAttr = nAttr.create('scale', 's', sx, sy, sz)
    nAttr.setWritable(False)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.outScaleAttr)
    zOBBTransform.output_attrs.append(zOBBTransform.outScaleAttr)

    px = create_numeric_attr('pivotX', 'px', om.MFnUnitAttribute.kDistance, niceName='Pivot X', writable=False, storable=False)
    py = create_numeric_attr('pivotY', 'py', om.MFnUnitAttribute.kDistance, niceName='Pivot Y', writable=False, storable=False)
    pz = create_numeric_attr('pivotZ', 'pz', om.MFnUnitAttribute.kDistance, niceName='Pivot Z', writable=False, storable=False)

    zOBBTransform.outPivotAttr = nAttr.create('pivot', 'piv', px, py, pz)
    nAttr.setWritable(False)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.outPivotAttr)

    # The pivot is only affected by the source, so we don't add it to output_attrs.
    # zOBBTransform.output_attrs.append(zOBBTransform.outPivotAttr)

    # Intermediate (internal):

    # Create internal attributes for updating the orig and current mesh attributes.
    zOBBTransform.updateOrigAttr = nAttr.create('updateOrig', 'updateOrig', om.MFnNumericData.kBoolean)
    nAttr.setHidden(True)
    nAttr.setConnectable(False)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.updateOrigAttr)

    zOBBTransform.updateCurrentAttr = nAttr.create('updateCurrent', 'updateCurrent', om.MFnNumericData.kBoolean)
    nAttr.setHidden(True)
    nAttr.setConnectable(False)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.updateCurrentAttr)

    # Inputs:
    input_attrs = []
    zOBBTransform.origMeshAttr = tAttr.create('inputMesh', 'in', om.MFnMeshData.kMesh)
    tAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.origMeshAttr)
    zOBBTransform.attributeAffects(zOBBTransform.origMeshAttr, zOBBTransform.updateOrigAttr)
    input_attrs.append(zOBBTransform.origMeshAttr)

    zOBBTransform.origMeshGroupIdAttr = nAttr.create('inputGroupId', 'ing', om.MFnNumericData.kLong)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.origMeshGroupIdAttr)
    zOBBTransform.attributeAffects(zOBBTransform.origMeshGroupIdAttr, zOBBTransform.updateOrigAttr)
    input_attrs.append(zOBBTransform.origMeshGroupIdAttr)

    zOBBTransform.currentMeshAttr = tAttr.create('currentMesh', 'cm', om.MFnMeshData.kMesh)
    tAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.currentMeshAttr)
    zOBBTransform.attributeAffects(zOBBTransform.currentMeshAttr, zOBBTransform.updateCurrentAttr)
    input_attrs.append(zOBBTransform.currentMeshAttr)

    zOBBTransform.currentMeshGroupIdAttr = nAttr.create('currentGroupId', 'cmg', om.MFnNumericData.kLong)
    nAttr.setStorable(False)
    zOBBTransform.addAttribute(zOBBTransform.currentMeshGroupIdAttr)
    zOBBTransform.attributeAffects(zOBBTransform.currentMeshGroupIdAttr, zOBBTransform.updateCurrentAttr)
    input_attrs.append(zOBBTransform.currentMeshGroupIdAttr)

    zOBBTransform.rotationModeAttr = enumAttr.create('rotationMode', 'rm')
    enumAttr.addField('None', 0)
    enumAttr.addField('Full', 1)
    enumAttr.addField('Primary', 2)
    enumAttr.addField('Secondary', 3)
    enumAttr.setDefault('Full')
    zOBBTransform.addAttribute(zOBBTransform.rotationModeAttr)
    input_attrs.append(zOBBTransform.rotationModeAttr)

    # Create three scale weight vectors.  The pr
    zOBBTransform.scaleWeightAttrs = []
    for longName, shortName, default in (('Primary', 'p', (1,0,0)), ('Secondary', 's', (0,1,0)), ('Tertiary', 't', (0,0,1))):
        psx = create_numeric_attr('scaleWeight%sX' % shortName.upper(), 'sw%sx' % shortName, om.MFnUnitAttribute.kDistance,
                niceName='%s axis scale weight' % longName, category='input', minValue=0, maxValue=1, default=default[0])
        psy = create_numeric_attr('scaleWeight%sY' % shortName.upper(), 'sw%sy' % shortName, om.MFnUnitAttribute.kDistance,
                niceName='%s axis scale weight' % longName, category='input', minValue=0, maxValue=1, default=default[1])
        psz = create_numeric_attr('scaleWeight%sZ' % shortName.upper(), 'sw%sz' % shortName, om.MFnUnitAttribute.kDistance,
                niceName='%s axis scale weight' % longName, category='input', minValue=0, maxValue=1, default=default[2])

        attr = nAttr.create('scaleWeight%s' % longName, 'sw' + shortName, psx, psy, psz)
        zOBBTransform.scaleWeightAttrs.append(attr)
        zOBBTransform.addAttribute(attr)
        input_attrs.append(attr)

    for output_attr in zOBBTransform.output_attrs:
        zOBBTransform.attributeAffects(zOBBTransform.updateCurrentAttr, output_attr)
        zOBBTransform.attributeAffects(zOBBTransform.updateOrigAttr, output_attr)

        # The input attributes affect the output.  Note that they don't affect the intermediate
        # update attributes.  Those are only affected by the input geometry.
        for input_attr in input_attrs:
            zOBBTransform.attributeAffects(input_attr, output_attr)

    zOBBTransform.attributeAffects(zOBBTransform.updateOrigAttr, zOBBTransform.outPivotAttr)

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zOBBTransform', zOBBTransform.pluginNodeId, creator, initialize, OpenMayaMPx.MPxNode.kDependNode)

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zOBBTransform.pluginNodeId)

