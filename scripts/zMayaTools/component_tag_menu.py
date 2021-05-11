import pymel.core as pm
from maya import OpenMaya as om
from zMayaTools import maya_helpers

# There are no commands for manipulating component tags yet, so we have to use
# internal classes.
if om.MGlobal.apiVersion() >= 20220000:
    import maya.internal.nodes.componenttags.ae_template as tag_tamplate

def find_injection_attr(shape_attr, tag):
    # A list of attributes where component tags can come from:
    component_tag_attrs = pm.geometryAttrInfo(shape_attr, outputPlugChain=True)
    component_tag_attrs = [pm.PyNode(attr) for attr in component_tag_attrs]

    injection_node = pm.PyNode(tag['node'])

    # Find an attribute in component_tag_attrs that lives on injection_node.
    for attr in component_tag_attrs:
        if attr.node() == injection_node:
            return attr

    return None

class ComponentTagContextMenu(object):
    @classmethod
    def register(cls):
        # Component sets are only supported from 2022 onwards.
        if om.MGlobal.apiVersion() < 20220000:
            return
        
        cls.deregister()
        pm.callbacks(hook='addRMBBakingMenuItems', addCallback=cls().add_context_menu_item, owner='zComponentTagMenu')
    
    @classmethod
    def deregister(cls):
        pm.callbacks(clearCallbacks=True, owner='zComponentTagMenu')

    def add_context_menu_item(self, item):
        self.current_node = pm.PyNode(item)
        if isinstance(self.current_node, pm.nodetypes.Transform):
            self.current_node = self.current_node.getShape()

        # Find the output attribute.
        if isinstance(self.current_node, pm.nodetypes.Mesh):
            self.current_attr = self.current_node.outMesh
        elif isinstance(self.current_node, pm.nodetypes.NurbsCurve):
            self.current_attr = self.current_node.local
        elif isinstance(self.current_node, pm.nodetypes.NurbsSurface):
            self.current_attr = self.current_node.local
        else:
            # The selection doesn't have component tags.
            return
    
        def cmd(unused1, unused2):
            self.build_top_context_menu(menu, item)
    
        # Add the top-level menu item.
        menu = pm.menuItem(label='Component Tags', subMenu=True, image='zMayaToolsIcon.png', postMenuCommand=cmd)
        pm.setParent('..', menu=True)
    
    def build_top_context_menu(self, parent, item):
        # Read the list of component tags.
        self.tags = pm.geometryAttrInfo(self.current_attr, componentTagHistory=True)

        # 2022 sometimes returns the same tag multiple times, so remove duplicates.  Duplicates from
        # different injection points is normal.
        self.tags = list({ (tag['key'],tag['node']): tag for tag in self.tags }.values())

        # Sort alphabetically.
        self.tags.sort(key=lambda item: item['key'])

        # Clear and populate the submenu.
        pm.setParent(parent, menu=True)
        pm.menu(parent, e=True, deleteAllItems=True)

        for tag in self.tags:
            # Only include the injection node in the menu if more than one node injects the same tag.
            include_injection_node = len([t for t in self.tags if t['key'] == tag['key']]) > 1
            self.add_component_tag_item(parent, tag, include_injection_node)

        # If we have at least one compnent tag, add a divider between it and Create.
        if self.tags:
            pm.menuItem(divider=True)

        def create(unused):
            tag_tamplate.ComponentTagsDlg.createDialog('pCubeShape1')
        pm.menuItem(label='Create component tag', command=create)

    def add_component_tag_item(self, parent, tag, include_injection_node):
        def select(unused):
            self.select_components_from_tag(self.current_attr, tag)

        label = tag['key']
        if include_injection_node:
             injection_node = pm.PyNode(tag['node'])
             label = '%s (%s)' % (label, injection_node.stripNamespace())

        # Choose an icon based on the component type.
        icons = {
            om.MFnGeometryData.kVerts: 'componentTag_vertex.png',
            om.MFnGeometryData.kEdges: 'componentTag_edge.png',
            om.MFnGeometryData.kFaces: 'componentTag_face.png',
        }
        icon = icons.get(tag['category'], '')
        pm.menuItem(label=label, command=select, image=icon)

    @classmethod
    def select_components_from_tag(cls, shape_attr, tag):
        injection_attr = find_injection_attr(shape_attr, tag)
        if not injection_attr:
            log.error('Couldn\'t find injection attribute')
            return

        # Select the component tag's geometry.
        components = pm.geometryAttrInfo(injection_attr, componentTagExpression=tag['key'], components=True)
        pm.select(clear=True)
        for component in components:
            pm.select('%s.%s' % (shape_attr.node(), component), add=True)

        # If we didn't select anything, select the mesh instead.
        if not pm.ls(sl=True):
            pm.select(shape_attr.node())

