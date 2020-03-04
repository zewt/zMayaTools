import pymel.core as pm
from maya import OpenMaya as om
from zMayaTools import maya_helpers

def get_parent_namespace(namespace):
    assert namespace != ''
    return ':'.join(namespace.split(':')[:-1])

class AssignMaterialsContextMenu(object):
    @classmethod
    def register(cls):
        cls.deregister()
        pm.callbacks(hook='addRMBBakingMenuItems', addCallback=cls().add_context_menu_item, owner='zAssignExistingMaterial')
    
    @classmethod
    def deregister(cls):
        pm.callbacks(clearCallbacks=True, owner='zAssignExistingMaterial')

    def add_context_menu_item(self, item):
        # If there's no selection, item is the most recently selected item, so assign
        # materials to that.  Otherwise, assign materials to all selected nodes.
        if pm.ls(sl=True):
            item = ''
    
        def cmd(unused1, unused2):
            self.build_top_context_menu(menu, item)
    
        # Add the top-level menu item.
        menu = pm.menuItem(label='zAssignExistingMaterial', subMenu=True, allowOptionBoxes=True, postMenuCommand=cmd)
        pm.setParent('..', menu=True)
    
    def create_namespace_submenu(self, namespace):
        def cmd(unused1, unused2):
            self.create_material_submenu(menu, namespace)

        # Add this namespace to its parent menu.
        menu = pm.menuItem(label=namespace.split(':')[-1], subMenu=True, allowOptionBoxes=True, pmc=cmd)
        pm.setParent('..', menu=True)

    def collect_materials(self):
        # Get all materials in the scene.
        shader_node_types = pm.listNodeTypes('shader')
        materials = pm.ls(type=shader_node_types)
    
        # Collect materials by namespace, and a list of child namespaces in each namespace that
        # contain materials.
        self.materials_by_namespace = {}
        self.namespaces_by_namespace = {}
        for material in materials:
            namespace = material.namespace().rstrip(':') # remove trailing :
            self.materials_by_namespace.setdefault(namespace, []).append(material)

            # Add this namespace to the parent namespace's list, and add each ancestor
            # namespace to its parent.  If namespaces don't have materials but they have
            # child namespaces that do, we still need to add them to the list.
            if namespace:
                namespace_parts = namespace.split(':')
                for idx in range(1, len(namespace_parts)+1):
                    child_namespace = ':'.join(namespace_parts[0:idx])
                    parent_namespace = get_parent_namespace(child_namespace)
                    self.namespaces_by_namespace.setdefault(parent_namespace, set()).add(child_namespace)

        # The namespace dict used sets to remove duplicates.  Replace the sets with lists.
        self.namespaces_by_namespace = {key: list(value) for key, value in self.namespaces_by_namespace.items()}

        # Sort each list alphabetically.
        for material_list in self.materials_by_namespace.values():
            material_list.sort(key=lambda node: node.stripNamespace().lower())
        for namespace_list in self.namespaces_by_namespace.values():
            namespace_list.sort(key=lambda namespace: namespace.lower())

    def build_top_context_menu(self, parent, item):
        self.current_item = item

        self.collect_materials()

        # Create the top-level submenu.
        self.create_material_submenu(parent, '')

    def create_material_submenu(self, parent, namespace):
        pm.setParent(parent, menu=True)
        pm.menu(parent, e=True, deleteAllItems=True)

        # Add namespaces at the top of the list.
        namespaces = self.namespaces_by_namespace.get(namespace, [])
        for child_namespace in namespaces:
            self.create_namespace_submenu(child_namespace)

        # Put a divider between namespaces and materials.
        materials = self.materials_by_namespace.get(namespace, [])
        if namespaces and materials:
            pm.menuItem(divider=True)

        # Add materials in this namespace.
        for material in materials:
            self.add_material_item(parent, material)

    def add_material_item(self, parent, material):
        def assign(unused):
            if self.current_item:
                pm.mel.eval('assignSG %s %s' % (material, self.current_item))
            else:
                pm.mel.eval('hyperShade -assign %s' % material)

        pm.menuItem(label=material.stripNamespace(), command=assign)

        def options(unused):
            pm.mel.eval('showEditor %s' % material)
        pm.menuItem(optionBox=True, command=options)

