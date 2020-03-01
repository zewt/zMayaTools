import math, sys
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaAnim as oma
import maya.api.OpenMayaRender as omr
from maya.OpenMaya import MGlobal
import pymel.core as pm
from zMayaTools.menus import Menu
from zMayaTools import maya_helpers, node_caching

# This is insane.  There are two Python APIs in Maya, and both of them are missing lots of
# stuff, and you can't mix them except in specific careful ways.
import maya.OpenMayaRender as v1omr
glRenderer = v1omr.MHardwareRenderer.theRenderer()
glFT = glRenderer.glFunctionTable()

def maya_useNewAPI(): pass

# Be careful when changing the order of these shapes.  Their index is the value of the .shape
# enum, so this affects the file format.
def _make_pyramid():
    return {
        'quads': [
            (-0.5, 0, +0.5),
            (+0.5, 0, +0.5),
            (+0.5, 0, -0.5),
            (-0.5, 0, -0.5),
        ],

        omr.MUIDrawManager.kTriangles: [
            (-0.5, 0, +0.5),
            (-0.5, 0, -0.5),
            (+0.0, 1, -0.0),

            (+0.5, 0, +0.5),
            (+0.5, 0, -0.5),
            (+0.0, 1, -0.0),

            (-0.5, 0, -0.5),
            (+0.5, 0, -0.5),
            (+0.0, 1, -0.0),

            (+0.5, 0, +0.5),
            (-0.5, 0, +0.5),
            (+0.0, 1, -0.0),
        ]
    }

def _make_ball():
    points = []
    p1 = (1.0) / 2.0
    p2 = (0.5) / 2.0
    for x in (1,-1):
        points.append((x*p1, -p2, -p2))
        points.append((x*p1, +p2, -p2))
        points.append((x*p1, +p2, +p2))
        points.append((x*p1, -p2, +p2))

        points.append((-p2, x*p1, -p2))
        points.append((+p2, x*p1, -p2))
        points.append((+p2, x*p1, +p2))
        points.append((-p2, x*p1, +p2))

        points.append((-p2, -p2, x*p1))
        points.append((+p2, -p2, x*p1))
        points.append((+p2, +p2, x*p1))
        points.append((-p2, +p2, x*p1))

        for y in (1,-1):
            points.append((-p2, x*+p2, y*+p1))
            points.append((+p2, x*+p2, y*+p1))
            points.append((+p2, x*+p1, y*+p2))
            points.append((-p2, x*+p1, y*+p2))

            points.append((x*+p2, -p2, y*+p1))
            points.append((x*+p2, +p2, y*+p1))
            points.append((x*+p1, +p2, y*+p2))
            points.append((x*+p1, -p2, y*+p2))

            points.append((x*+p2, y*+p1, -p2))
            points.append((x*+p2, y*+p1, +p2))
            points.append((x*+p1, y*+p2, +p2))
            points.append((x*+p1, y*+p2, -p2))

    tris = []
    for x in (1, -1):
        for y in (1, -1):
            for z in (1, -1):
                tris.append((x*-p1, y*-p2, z*p2))
                tris.append((x*-p2, y*-p1, z*p2))
                tris.append((x*-p2, y*-p2, z*p1))
    
    return {
        'quads': points,
        omr.MUIDrawManager.kTriangles: tris,
    }

# A slightly larger shape that can sit around the others.  This is useful for things like
# pivots.
def _make_orbit():
    def make_box(x, y, z):
        s = 1/6.0
        box = [
            (-s, -s, +s), # top
            (+s, -s, +s),
            (+s, -s, -s),
            (-s, -s, -s),

            (-s, +s, +s), # bottom
            (+s, +s, +s),
            (+s, +s, -s),
            (-s, +s, -s),

            (-s, -s, +s), # left
            (-s, +s, +s),
            (-s, +s, -s),
            (-s, -s, -s),

            (+s, -s, +s), # right
            (+s, +s, +s),
            (+s, +s, -s),
            (+s, -s, -s),

            (-s, +s, +s), # front
            (+s, +s, +s),
            (+s, -s, +s),
            (-s, -s, +s),

            (-s, +s, -s), # back
            (+s, +s, -s),
            (+s, -s, -s),
            (-s, -s, -s),
        ]

        result = []
        for vx, vy, vz in box:
            result.append((vx + x, vy + y, vz + z))
        return result

    boxes = []
    boxes.extend(make_box(-1, 0, 0))
    boxes.extend(make_box(+1, 0, 0))
    boxes.extend(make_box( 0, 0,+1))
    boxes.extend(make_box( 0, 0,-1))

    return {
        'quads': boxes
    }


shapes = [{
    'name': 'Ball',
    'geometry': _make_ball(),
}, {
    'name': 'Pyramid',
    'geometry': _make_pyramid(),
}, {
    'name': 'Pivot',
    'geometry': _make_orbit(),
}]

def _convert_shape(shape):
    geometry = shape['geometry']
    lines = geometry.setdefault(omr.MUIDrawManager.kLines, [])

    # Add edge lines for quads.
    if 'quads' in geometry:
        quads = geometry['quads']
        for i in xrange(0, len(quads), 4):
            lines.append(quads[i+0])
            lines.append(quads[i+1])
            lines.append(quads[i+1])
            lines.append(quads[i+2])
            lines.append(quads[i+2])
            lines.append(quads[i+3])
            lines.append(quads[i+3])
            lines.append(quads[i+0])

    # Add edge lines for tris.
    if omr.MUIDrawManager.kTriangles in geometry:
        tris = geometry[omr.MUIDrawManager.kTriangles]
        for i in xrange(0, len(tris), 3):
            lines.append(tris[i+0])
            lines.append(tris[i+1])
            lines.append(tris[i+1])
            lines.append(tris[i+2])
            lines.append(tris[i+2])
            lines.append(tris[i+0])

    # Convert quads to tris.
    if 'quads' in geometry:
        tris = geometry.setdefault(omr.MUIDrawManager.kTriangles, [])
        quads = geometry.pop('quads')

        for i in xrange(0, len(quads), 4):
            tris.append(quads[i+0])
            tris.append(quads[i+1])
            tris.append(quads[i+2])

            tris.append(quads[i+2])
            tris.append(quads[i+3])
            tris.append(quads[i+0])
    
    for key, data in geometry.items():
        array = om.MPointArray()
        for point in data:
            array.append(om.MPoint(*point))

        geometry[key] = array

    return shape

shapes = [_convert_shape(shape) for shape in shapes]

def _getCustomShape(node):
    # Return the shape connected to customMeshAttr.
    depNode = om.MFnDependencyNode(node)
    obj = depNode.userNode()
    dataBlock = obj.forceCache()
    meshHandle = dataBlock.inputValue(zRigHandle.customMeshAttr)
    try:
        it = om.MItMeshPolygon(meshHandle.asMesh())
    except RuntimeError:
        # We'll get "kInvalidParameter: Argument is a NULL pointer" if there's no
        # mesh connection.  How do we check this?
        return shapes[0]['geometry']

    tris = []
    lines = []
    for face in maya_helpers.iterate_mesh(it):
        face = it.getPoints(om.MSpace.kObject)

        # The data from the iterator doesn't stay valid, so make a copy of the point.
        face = [om.MPoint(v) for v in face]

        if len(face) == 3:
            tris.extend(face)
            lines.extend((face[0], face[1], face[1], face[2], face[2], face[0]))
        elif len(face) == 4:
            tris.extend((face[0], face[1], face[2], face[2], face[3], face[0]))
            lines.extend((face[0], face[1], face[1], face[2], face[2], face[3], face[3], face[0]))
        else:
            # We don't currently support meshes with more than four faces.  We could
            # triangulate with MFnMesh.polyTriangulate, but I'm not sure it's worth
            # the bother.
            pass

    return {
        omr.MUIDrawManager.kTriangles: tris,
        omr.MUIDrawManager.kLines: lines,
    }

def getShapeBounds(shape):
    boundingBox = om.MBoundingBox()
    for item in shape.values():
        for point in item:
            boundingBox.expand(point)

    return boundingBox

def _transformShape(shape, transform):
    result = {}
    for key, data in shape.items():
        result[key] = om.MPointArray([v*transform for v in data])

    return result

class zRigHandle(om.MPxSurfaceShape):
    id = om.MTypeId(0x124743)
    drawDbClassification = "drawdb/geometry/zRigHandle"
    drawRegistrantId = "zRigHandlePlugin"

    def __init__(self):
        om.MPxSurfaceShape.__init__(self)

    @classmethod
    def creator(cls):
        return cls()

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()
        enumAttr = om.MFnEnumAttribute()
        matAttr = om.MFnMatrixAttribute()
        uAttr = om.MFnUnitAttribute()
        typedAttr = om.MFnTypedAttribute()

        cls.shapeAttr = enumAttr.create('shape', 'sh', 0)
        enumAttr.addField('Custom', -1)
        for idx, shape in enumerate(shapes):
            enumAttr.addField(shape['name'], idx)
        enumAttr.channelBox = True
        cls.addAttribute(cls.shapeAttr)

        cls.customMeshAttr = typedAttr.create("inCustomMesh", "icm", om.MFnMeshData.kMesh)
        typedAttr.storable = False
        # The kReset constant is missing from the Python 2.0 API.
        typedAttr.disconnectBehavior = 1
        cls.addAttribute(cls.customMeshAttr)

        cls.transformAttr = matAttr.create('transform', 't', om.MFnMatrixAttribute.kFloat)
        matAttr.keyable = False
        cls.addAttribute(cls.transformAttr)

        localRotateX = uAttr.create('localRotateX', 'lrx', om.MFnUnitAttribute.kAngle, 0.0)
        localRotateY = uAttr.create('localRotateY', 'lry', om.MFnUnitAttribute.kAngle, 0.0)
        localRotateZ = uAttr.create('localRotateZ', 'lrz', om.MFnUnitAttribute.kAngle, 0.0)
        cls.localRotateAttr = nAttr.create('localRotate', 'lr', localRotateX, localRotateY, localRotateZ)
        nAttr.channelBox = True
        nAttr.keyable = False
        cls.addAttribute(cls.localRotateAttr)

        cls.localTranslateAttr = nAttr.createPoint('localPosition', 'lp')
        nAttr.channelBox = True
        nAttr.keyable = False
        cls.addAttribute(cls.localTranslateAttr)

        localScaleX = nAttr.create('localScaleX', 'lsx', om.MFnNumericData.kFloat, 1)
        localScaleY = nAttr.create('localScaleY', 'lsy', om.MFnNumericData.kFloat, 1)
        localScaleZ = nAttr.create('localScaleZ', 'lsz', om.MFnNumericData.kFloat, 1)
        cls.localScaleAttr = nAttr.create('localScale', 'ls', localScaleX, localScaleY, localScaleZ)
        nAttr.channelBox = True
        nAttr.keyable = False
        cls.addAttribute(cls.localScaleAttr)

        cls.colorAttr = nAttr.createColor('color', 'dc')
        nAttr.default = (.38,0,0.02)
        cls.addAttribute(cls.colorAttr)

        cls.alphaAttr = nAttr.create('alpha', 'a', om.MFnNumericData.kFloat, 0.333)
        nAttr.setSoftMin(0)
        nAttr.setSoftMax(1)
        nAttr.keyable = False
        cls.addAttribute(cls.alphaAttr)

        cls.borderColorAttr = nAttr.createColor('borderColor', 'bc')
        nAttr.default = (-1,-1,-1)
        cls.addAttribute(cls.borderColorAttr)

        cls.borderAlphaAttr = nAttr.create('borderAlpha', 'ba', om.MFnNumericData.kFloat, 1)
        nAttr.setSoftMin(0)
        nAttr.setSoftMax(1)
        nAttr.keyable = False
        cls.addAttribute(cls.borderAlphaAttr)

        cls.xrayAttr = nAttr.create('xray', 'xr', om.MFnNumericData.kBoolean, True)
        nAttr.keyable = False
        nAttr.channelBox = True
        cls.addAttribute(cls.xrayAttr)

    def postConstructor(self):
        self.isRenderable = True

        depNode = om.MFnDependencyNode(self.thisMObject())
        depNode.setName("rigHandleShape#");

    def setDependentsDirty(self, plug, affectedPlugs):
        if plug.isChild:
            plug = plug.parent()

        if plug in (self.transformAttr, self.localTranslateAttr, self.localRotateAttr, self.localScaleAttr):
            # Discard our transformed shape.
            if hasattr(self, 'transformedShape'): del self.transformedShape

        if plug in (self.transformAttr, self.shapeAttr,
            self.localTranslateAttr, self.localRotateAttr, self.localScaleAttr,
            self.colorAttr, self.alphaAttr, self.borderColorAttr, self.borderAlphaAttr,
            self.xrayAttr, self.customMeshAttr):
            self.childChanged(self.kBoundingBoxChanged)
            omr.MRenderer.setGeometryDrawDirty(self.thisMObject(), True)

        if plug in (self.shapeAttr, self.customMeshAttr):
            # Discard our shape cache.  We can't set the new one now, since the new
            # plug value hasn't actually been set yet, so we'll do it on the next
            # render.
            if hasattr(self, 'transformedShape'): del self.transformedShape
            if hasattr(self, 'shape'): del self.shape

            self.childChanged(self.kBoundingBoxChanged)

        return super(zRigHandle, self).setDependentsDirty(plug, affectedPlugs)

    def getShapeSelectionMask(self):
        # Set both kSelectMeshes, so tumble on pivot sees the object, and kSelectJoints, so we're
        # higher priority for selection than meshes that are in front of us.  Xray alone won't do
        # this.
        mask = om.MSelectionMask()
#        mask.addMask(om.MSelectionMask.kSelectMeshes)
        mask.addMask(om.MSelectionMask.kSelectJoints)
        return mask

    def isBounded(self):
        return True

    def getShapeIdx(self):
        return om.MPlug(self.thisMObject(), self.shapeAttr).asShort()
        
    def getShape(self):
        # If the shape isn't cached, cache it now.
        if not hasattr(self, 'shape'):
            self.shape = self._getShapeFromPlug()

        if not hasattr(self, 'transformedShape'):
            shape = self.shape

            transform = self._getLocalTransform()
            self.transformedShape = _transformShape(shape, transform)

        return self.transformedShape

    def _getShapeFromPlug(self):
        idx = self.getShapeIdx()
        if idx == -1:
            shape = _getCustomShape(self.thisMObject())
        else:
            shape = shapes[idx]['geometry']

        return shape

    def _getLocalTransform(self):
        node = self.thisMObject()

        transformPlug = om.MPlug(node, self.transformAttr)
        transform = om.MFnMatrixData(transformPlug.asMObject()).matrix()

        mat = om.MTransformationMatrix(transform)

        # Apply local translation.
        localTranslatePlug = om.MPlug(node, self.localTranslateAttr)
        localTranslation = om.MVector(*[localTranslatePlug.child(idx).asFloat() for idx in range(3)])
        mat.translateBy(localTranslation, om.MSpace.kObject)

        # Apply local rotation.
        localRotatePlug = om.MPlug(node, self.localRotateAttr)
        localRotatePlugs = [localRotatePlug.child(idx) for idx in range(3)]
        localRotate = om.MVector(*[localRotatePlugs[idx].asMAngle().asRadians() for idx in range(3)])
        mat.rotateBy(om.MEulerRotation(localRotate), om.MSpace.kObject)

        # Apply local scale.
        scalePlug = om.MPlug(node, self.localScaleAttr)
        scale = om.MFnNumericData(scalePlug.asMObject()).getData()
        mat.scaleBy(scale, om.MSpace.kObject)

        return mat.asMatrix()

    @property
    def xray(self):
        return om.MPlug(self.thisMObject(), self.xrayAttr).asBool()

    def boundingBox(self):
        return getShapeBounds(self.getShape())

def _hitTestShape(view, shape):
    # Hit test shape within view.
    for itemType, data in shape.items():
        view.beginSelect()

        glFT.glBegin(v1omr.MGL_TRIANGLES)
        for v in data:
            glFT.glVertex3f(v.x, v.y, v.z)
        glFT.glEnd()

        # Check the hit test.
        if view.endSelect() > 0:
            return True

    return False


# This object isn't created in 2016.5 VP2.
class zRigHandleShapeUI(omui.MPxSurfaceShapeUI):
    def __init__(self):
        omui.MPxSurfaceShapeUI.__init__(self)

    @staticmethod
    def creator():
        return zRigHandleShapeUI()

    def select(self, selectInfo, selectionList, worldSpaceSelectPts):
        shape = self.surfaceShape().getShape()

        # Hit test the selection against the shape.
        if not _hitTestShape(selectInfo.view(), shape):
            return False

        item = om.MSelectionList()
        item.add(selectInfo.selectPath())

        # Get the world space position of the node.  We'll set the position of the selection here,
        # so the camera focuses on it.
        mat = item.getDagPath(0).inclusiveMatrix()
        transformation = om.MTransformationMatrix(mat)
        pos = transformation.translation(om.MSpace.kWorld)

        priorityMask = om.MSelectionMask(om.MSelectionMask.kSelectJoints)
        selectInfo.addSelection(item, om.MPoint(pos), selectionList, worldSpaceSelectPts, priorityMask, False)

        return True


def isPathSelected(objPath):
    sel = om.MGlobal.getActiveSelectionList()
    if sel.hasItem(objPath):
        return True

    objPath = om.MDagPath(objPath)
    objPath.pop()
    if sel.hasItem(objPath):
        return True
    return False

class zRigHandleDrawOverride(omr.MPxDrawOverride):
    @staticmethod
    def creator(obj):
        return zRigHandleDrawOverride(obj)

    @staticmethod
    def draw(context, data):
        return

    def __init__(self, obj):
        super(zRigHandleDrawOverride, self).__init__(obj, self.draw, False)

    def supportedDrawAPIs(self):
        return omr.MRenderer.kOpenGL | omr.MRenderer.kDirectX11 | omr.MRenderer.kOpenGLCoreProfile

    def isBounded(self, objPath, cameraPath):
        return True

    def boundingBox(self, objPath, cameraPath):
        depNode = om.MFnDependencyNode(objPath.node())
        obj = depNode.userNode()
        return obj.boundingBox()

    def disableInternalBoundingBoxDraw(self):
        return True

    def prepareForDraw(self, objPath, cameraPath, frameContext, oldData):
        depNode = om.MFnDependencyNode(objPath.node())
        obj = depNode.userNode()
    
        isSelected = isPathSelected(objPath)
        self.xray = obj.xray

        plug = om.MPlug(objPath.node(), zRigHandle.colorAttr)
        self.color = om.MColor(om.MFnNumericData(plug.asMObject()).getData())

        alpha = om.MPlug(objPath.node(), zRigHandle.alphaAttr).asFloat()
        self.color.a = alpha

        if isSelected:
            self.borderColor = omr.MGeometryUtilities.wireframeColor(objPath)
        else:
            plug = om.MPlug(objPath.node(), zRigHandle.borderColorAttr)
            self.borderColor = om.MColor(om.MFnNumericData(plug.asMObject()).getData())

            # If no color has been set and we're on the default of (-1,-1,-1), use the main color,
            # so in the common case where you want to use the same color you don't have to set both.
            if self.borderColor.r == -1 and self.borderColor.g == -1 and self.borderColor.b == -1:
                self.borderColor = om.MColor(self.color)

            self.borderColor.a = om.MPlug(objPath.node(), zRigHandle.borderAlphaAttr).asFloat()

        self.shape = obj.getShape()

    def hasUIDrawables(self):
        return True

    def addUIDrawables(self, objPath, drawManager, frameContext, data):
        if self.xray:
            drawManager.beginDrawInXray()

        drawManager.beginDrawable()
        for itemType, data in self.shape.items():
            if itemType == omr.MUIDrawManager.kLines:
                # X-ray only
                continue
            
            drawManager.setColor(self.color)
            drawManager.mesh(itemType, data)

        lines = self.shape.get(omr.MUIDrawManager.kLines)
        if lines:
            drawManager.setColor(self.borderColor)
            drawManager.mesh(omr.MUIDrawManager.kLines, lines)

        drawManager.endDrawable()

        if self.xray:
            drawManager.endDrawInXray()

class PluginMenu(Menu):
    def add_menu_items(self):
        # Add "Rig Handle" after "Locator" in Create > Construction Aids.
        def create(arg):
            node = pm.createNode('zRigHandle')
            pm.select(node.getTransform())

        pm.mel.eval('ModCreateMenu "mainCreateMenu"')
        menu = 'mainCreateMenu'
        menu_items = pm.menu(menu, q=True, ia=True)
        idx = self.find_item_with_command(menu_items, 'CreateLocator')
        self.add_menu_item('zRigHandle', label="Rig Handle", command=create,
                insertAfter=menu_items[idx], parent=menu,
                image='zRigHandle.png',
                annotation='Create a viewport rig handle',
                top_level_path='Rigging|Rig_Handle')

menu = PluginMenu()
def initializePlugin(obj):
    plugin = om.MFnPlugin(obj)
    plugin.registerShape('zRigHandle', zRigHandle.id, zRigHandle.creator, zRigHandle.initialize, zRigHandleShapeUI.creator, zRigHandle.drawDbClassification)
    omr.MDrawRegistry.registerDrawOverrideCreator(zRigHandle.drawDbClassification, zRigHandle.drawRegistrantId, zRigHandleDrawOverride.creator)

    menu.add_menu_items()
    node_caching.enable_caching_for_node_name('zRigHandle')
    pm.pluginDisplayFilter('zRigHandle', classification=zRigHandle.drawDbClassification, register=True, label='Rig Handles')

def uninitializePlugin(obj):
    plugin = om.MFnPlugin(obj)
    omr.MDrawRegistry.deregisterDrawOverrideCreator(zRigHandle.drawDbClassification, zRigHandle.drawRegistrantId)
    plugin.deregisterNode(zRigHandle.id)

    menu.remove_menu_items()
    node_caching.disable_caching_for_node_name('zRigHandle')
    pm.pluginDisplayFilter('zRigHandle', deregister=True)

