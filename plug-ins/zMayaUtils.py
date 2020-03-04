import os
from pymel import core as pm
from maya import OpenMaya as om, OpenMayaMPx as ompx
import zMayaTools.menus
from zMayaTools.menus import Menu
from zMayaTools import controller_editor, maya_helpers, material_assignment_menu, shelf_menus, joint_labelling, skin_clusters
from zMayaTools import animation_helpers, pick_walk, wireframes
try:
    from importlib import reload
except ImportError:
    pass

from zMayaTools import maya_logging
log = maya_logging.get_log()

# Only import hide_output_window in Windows.
if os.name == 'nt':
    from zMayaTools import hide_output_window
    reload(hide_output_window)

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()

        self.shelf_menu = None
        self.shelf_preference_handler = None

    def add_menu_items(self):
        super(PluginMenu, self).add_menu_items()

        # Make sure the file menu and other deferred menus are built.
        pm.mel.eval('buildDeferredMenus()')

        if os.name == 'nt':
            # This would be more logical to put in the top "Open" block, but we don't put it
            # there to avoid shifting around the important open/save menu items (shifting those
            # down would be annoying since you expect them to be a certain distance from the menu).
            # This is also not an important enough feature to put in such a high-profile place.
            # Instead, put it down in the "View" section.
            menu = 'mainFileMenu'
            def show_scene_in_explorer(unused):
                maya_helpers.open_scene_in_explorer()

            # It would be useful to grey the menu item out if the scene hasn't been saved, but there's
            # only a global callback for the menu and not for each menu item, and adding to the menu
            # callback is brittle.
            section = self.find_menu_section_containing_item(pm.menu('mainFileMenu', q=True, ia=True), 'viewSequenceItem')

            self.add_menu_item('zMayaTools_ViewSceneInExplorer', label='View Scene In Explorer', parent=menu, insertAfter=section[-1],
                    annotation='Show the current scene file in Explorer',
                    command=show_scene_in_explorer,
                    top_level_path='Misc|ViewSceneInExplorer')

        pm.mel.eval('ChaSkinningMenu("mainRigSkinningMenu")')
        self.add_menu_item('zMayaTools_ToggleMoveSkinnedJoints', label='Toggle Move Skinned Joints', parent=pm.mel.globals['gRigSkinningMenu'],
                insertAfter='moveSkinJointsItem',
                command='zMoveSkinnedJoints -toggle',
                sourceType='mel',
                image='smoothSkin.png',
                top_level_path='Rigging|ToggleMoveSkinnedJoints')

        self.add_menu_item('zMayaTools_CreateEditableJoints', label='Create Editable Joints', parent=pm.mel.globals['gRigSkinningMenu'],
                insertAfter='zMayaTools_ToggleMoveSkinnedJoints',
                command='zCreateEditableJoints',
                sourceType='mel',
                image='smoothSkin.png',
                top_level_path='Rigging|CreateEditableJoints')
        
        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        def validate_character(unused):
            from zMayaTools import validate_character
            reload(validate_character)
            validate_character.UI().run()

        self.add_menu_item('zMayaTools_ValidateCharacter', label='Validate Character', parent=menu, insertAfter='hikWindowItem',
                command=validate_character,
                top_level_path='Rigging|ValidateCharacter')

        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            # Add "Mirror Weights" in the "Weights" section at the bottom of the Deform menu.
            menu_items = pm.menu(menu, q=True, ia=True)
            mirror_weights = self.find_item_with_command(menu_items, 'MirrorDeformerWeights')

            def run_copy_painted_weights(unused):
                from zMayaTools import copy_painted_weights
                reload(copy_painted_weights)
                ui = copy_painted_weights.UI()
                ui.run()

            self.add_menu_item('zMayaTools_CopyWeights_%s' % menu, label='Copy Deformer Weights', parent=menu,
                    annotation='Copy painted weights from one mesh to another',
                    insertAfter=menu_items[mirror_weights],
                    command=run_copy_painted_weights,
                    top_level_path='Rigging|CopyWeights')
            
            # Find the "Edit" section in the Deform menu, then find the "Blend Shape" submenu inside
            # that section.
            menu_items = pm.menu(menu, q=True, ia=True)
            section = self.find_menu_section_by_name(menu_items, pm.mel.eval('uiRes("m_ChaDeformationsMenu.kDeformEdit")'))
            submenu = self.find_submenu_by_name(section, 'Blend Shape', default=menu)
                
            def run_blend_shape_retargetting(unused):
                from zMayaTools import blend_shape_retargetting
                reload(blend_shape_retargetting)
                blend_shape_retargetting.UI().run()

            self.add_menu_item('zBlendShapeRetargetting_%s' % menu, label='Retarget Blend Shapes', parent=submenu,
                    command=run_blend_shape_retargetting,
                    image='blendShape.png',
                    top_level_path='Blend Shapes|RetargetBlendShapes')

            def run_split_blend_shapes(unused):
                from zMayaTools import split_blend_shapes
                split_blend_shapes.UI().run()

            self.add_menu_item('zSplitBlendShape_%s' % menu, label='Split Blend Shape', parent=submenu,
                    annotation='Split a blend shape across a plane',
                    command=run_split_blend_shapes,
                    image='blendShape.png',
                    top_level_path='Blend Shapes|SplitBlendShapes')

        self.add_rigging_tools()
        self.add_hide_output_window()
        self.add_show_shelf_menus()
        self.add_channel_box_editing()
        self.add_modify_menu_items()
        controller_editor.menu.add_menu_items()
        joint_labelling.menu.add_menu_items()

    def add_rigging_tools(self):
        menu = 'MayaWindow|mainRigControlMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaControlsMenu "%s";' % menu)

        # If this ends up having a bunch of rigging tools this can be a submenu, but
        # for now just put this at the top.
        divider = self.add_menu_item('zMayaTools_RiggingDivider', divider=True, parent=menu, label='zMayaUtils')

        def run_eye_rig(unused):
            from zMayaTools.rigging import eye_rig
            eye_rig.create_eye_rig()
            
        self.add_menu_item('zMayaTools_EyeRig', label='Eye Rig', parent=menu, insertAfter=divider,
                command=run_eye_rig,
                top_level_path='Rigging|EyeRig')

    def add_hide_output_window(self):
        # Add "Show Output Window" at the end of the Windows menu.
        if os.name != 'nt':
            return

        # Activate the user's current preference.
        hide_output_window.refresh_visibility()

        def refresh_menu_item():
            label = 'Show Output Window' if hide_output_window.is_hidden() else 'Hide Output Window'
            for menu_item in self.output_window_menu_items:
                pm.menuItem(menu_item, e=True, label=label)

        def toggle_output_window(unused):
            hide_output_window.toggle()
            refresh_menu_item()

        pm.mel.eval('buildDeferredMenus')
        menu_item = self.add_menu_item('zHideOutputWindow', parent='mainWindowMenu', command=toggle_output_window,
                label='Hide output window', # placeholder
                top_level_path='Misc|ToggleOutputWindow')
        self.output_window_menu_items = self.get_related_menu_items(menu_item)
        refresh_menu_item()

    def add_show_shelf_menus(self):
        self.shelf_menu = shelf_menus.ShelfMenu()
        self.shelf_preference_handler = shelf_menus.create_preference_handler()
        self.shelf_preference_handler.register()

    def add_channel_box_editing(self):
        def move_attr_up(unused):
            from zMayaTools import attribute_reordering
            reload(attribute_reordering)
            attribute_reordering.move_selected_attr(down=False)

        def move_attr_down(unused):
            from zMayaTools import attribute_reordering
            reload(attribute_reordering)
            attribute_reordering.move_selected_attr(down=True)

        # Add "Move Attributes Up" and "Move Attributes Down" to the bottom of Edit.
        # Put this in a submenu, so the menu can be torn off while making a bunch of
        # attribute edits.
        #
        # The top_level_paths are set to make "Move Up" come before "Move Down" in the
        # standalone menu.
        menu = 'MayaWindow|mainEditMenu'
        move_attribute_menu = self.add_menu_item('zMayaTools_MoveAttributes', label='Reorder Attributes', parent=menu,
                subMenu=True, tearOff=True)
        self.add_menu_item('zMayaTools_MoveAttributeUp', label='Move Attributes Up', parent=move_attribute_menu,
                command=move_attr_up,
                annotation='Move a channel box attribute higher in the list',
                top_level_path='Reorder Attributes|Move1')
        self.add_menu_item('zMayaTools_MoveAttributeDown', label='Move Attributes Down', parent=move_attribute_menu,
                command=move_attr_down,
                annotation='Move a channel box attribute lower in the list',
                top_level_path='Reorder Attributes|Move2')

    def add_modify_menu_items(self):
        # Add Match Translation and Rotation to Modify > Match Transformations.
        # This menu item isn't added to the top-level zMayaTools menu, since it doesn't
        # really make sense on its own.
        pm.mel.eval('ModObjectsMenu "mainModifyMenu"')
        menu = 'mainModifyMenu|matchTransformsItem'
        menu_items = pm.menu(menu, q=True, ia=True)
        match_rotation = self.find_item_with_command(menu_items, 'MatchRotation')

        self.add_menu_item('zMayaTools_MatchPosition', label='Match Position',
                parent=menu,
                annotation='Match the translation and rotation of selected objects to the last-selected object.',
                insertAfter=menu_items[match_rotation],
                command='zMatchPosition', sourceType='mel')

    def remove_menu_items(self):
        super(PluginMenu, self).remove_menu_items()

        # Remove shelf menus.
        if self.shelf_menu is not None:
            self.shelf_menu.remove()
            self.shelf_menu = None

        if self.shelf_preference_handler is not None:
            self.shelf_preference_handler.unregister()
            self.shelf_preference_handler = None

        controller_editor.menu.remove_menu_items()
        joint_labelling.menu.remove_menu_items()

menu = PluginMenu()
def initializePlugin(mobject):
    plugin = ompx.MFnPlugin(mobject)
    if om.MGlobal.mayaState() != om.MGlobal.kInteractive:
        return

    menu.add_menu_items()
    material_assignment_menu.AssignMaterialsContextMenu.register()
    skin_clusters.MoveSkinnedJoints.register(plugin)
    animation_helpers.setup_runtime_commands()
    pick_walk.setup_runtime_commands()
    maya_helpers.setup_runtime_commands()
    wireframes.setup_runtime_commands()

def uninitializePlugin(mobject):
    plugin = ompx.MFnPlugin(mobject)
    menu.remove_menu_items()
    material_assignment_menu.AssignMaterialsContextMenu.deregister()
    skin_clusters.MoveSkinnedJoints.deregister(plugin)

