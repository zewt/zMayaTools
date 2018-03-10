import os
from pymel import core as pm
from maya import OpenMaya as om
from zMayaTools.menus import Menu
from zMayaTools import controller_editor, maya_helpers, shelf_menus
reload(controller_editor)

from zMayaTools import maya_logging
log = maya_logging.get_log()

# Only import hide_output_window in Windows.
if os.name == 'nt':
    from zMayaTools import hide_output_window
    reload(hide_output_window)

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()

        self.optvars = maya_helpers.OptionVars()
        self.optvars.add('zShowShelfMenus', 'bool', False)

        self.shelf_menu = None
        self.controller_ui = None

    def add_menu_items(self):
        menu = 'MayaWindow|mainRigSkeletonsMenu'


        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)


        def validate_character(unused):
            from zMayaTools import validate_character
            reload(validate_character)
            validate_character.UI().run()

        validate = self.add_menu_item('zMayaTools_ValidateCharacter', label='Validate Character', parent=menu, insertAfter='hikWindowItem',
                command=validate_character)

        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            # Add "Mirror Weights" in the "Weights" section at the bottom of the Deform menu.
            menu_items = pm.menu(menu, q=True, ia=True)
            mirror_weights = self.find_item_by_name(menu_items, 'Mirror Deformer Weights')

            def run_copy_painted_weights(unused):
                from zMayaTools import copy_painted_weights
                reload(copy_painted_weights)
                ui = copy_painted_weights.UI()
                ui.run()

            self.add_menu_item('zMayaTools_CopyWeights_%s' % menu, label='Copy Deformer Weights', parent=menu,
                    annotation='Copy painted weights from one mesh to another',
                    insertAfter=menu_items[mirror_weights],
                    command=run_copy_painted_weights)
            
            # Find the "Edit" section in the Deform menu, then find the "Blend Shape" submenu inside
            # that section.
            menu_items = pm.menu(menu, q=True, ia=True)
            section = self.find_menu_section_by_name(menu_items, 'Edit')
            submenu = self.find_submenu_by_name(section, 'Blend Shape', default=menu)
                
            def run_blend_shape_retargetting(unused):
                from zMayaTools import blend_shape_retargetting
                blend_shape_retargetting.UI().run()

            self.add_menu_item('zBlendShapeRetargetting_%s' % menu, label='Retarget Blend Shapes', parent=submenu,
                    command=run_blend_shape_retargetting)

            def run_split_blend_shapes(unused):
                from zMayaTools import split_blend_shapes
                split_blend_shapes.UI().run()

            self.add_menu_item('zSplitBlendShape_%s' % menu, label='Split Blend Shape', parent=submenu,
                    annotation='Split a blend shape across a plane',
                    command=run_split_blend_shapes)

        self.add_rigging_tools()
        self.add_hide_output_window()
        self.add_show_shelf_menus()
        self.add_controller_editor_menu_item()

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
            
        eye_rig = self.add_menu_item('zMayaTools_EyeRig', label='Eye Rig', parent=menu, insertAfter=divider,
                command=run_eye_rig)

    def add_hide_output_window(self):
        # Add "Show Output Window" at the end of the Windows menu.
        if os.name != 'nt':
            return

        # Activate the user's current preference.
        hide_output_window.refresh_visibility()

        def refresh_menu_item():
            label = 'Show Output Window' if hide_output_window.is_hidden() else 'Hide Output Window'
            pm.menuItem(self.output_window_menu_item, e=True, label=label)

        def toggle_output_window(unused):
            hide_output_window.toggle()
            refresh_menu_item()

        pm.mel.eval('buildDeferredMenus')
        self.output_window_menu_item = self.add_menu_item('zHideOutputWindow', parent='mainWindowMenu', command=toggle_output_window)
        refresh_menu_item()

    def add_show_shelf_menus(self):
        # Add "Show Shelf Menus" at the end of the Windows menu.
        self.shelf_menu = None

        def refresh():
            # Update the menu item.
            label = 'Hide Shelf Menus' if self.optvars['zShowShelfMenus'] else 'Show Shelf Menus'
            pm.menuItem(self.shelf_menus_menu_item, e=True, label=label)

            # Show or hide the menu items.
            if self.optvars['zShowShelfMenus'] and self.shelf_menu is None:
                self.shelf_menu = shelf_menus.ShelfMenu()
            elif not self.optvars['zShowShelfMenus'] and self.shelf_menu is not None:
                self.shelf_menu.remove()
                self.shelf_menu = None

        def toggle_shelf_menus(unused):
            self.optvars['zShowShelfMenus'] = not self.optvars['zShowShelfMenus']
            refresh()

        pm.mel.eval('buildDeferredMenus')
        self.shelf_menus_menu_item = self.add_menu_item('zShowShelfMenus', parent='mainWindowMenu', command=toggle_shelf_menus)
        refresh()

    def add_controller_editor_menu_item(self):
        def open_controller_editor(unused):
            reload(controller_editor)
            if self.controller_ui is None:
                self.controller_ui = controller_editor.ControllerEditor()
                def closed():
                    self.controller_ui = None
                self.controller_ui.destroyed.connect(closed)

            # Disable retain, or we won't be able to create the window again after reloading the script
            # with an "Object's name 'DialogWorkspaceControl' is not unique" error.
            self.controller_ui.show(dockable=True, retain=False)

        menu = 'MayaWindow|mainRigControlMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaControlsMenu "%s";' % menu)

        # Add "Edit Controllers" at the end of the "Controller" section of Control.
        menu_items = pm.menu(menu, q=True, ia=True)
        controller_section = self.find_menu_section_by_name(menu_items, 'Controller')

        self.add_menu_item('zMayaTools_ControllerEditor', label='Edit Controllers', parent=menu,
                insertAfter=controller_section[-1],
                command=open_controller_editor)


    def remove_menu_items(self):
        super(PluginMenu, self).remove_menu_items()

        # Remove shelf menus.
        if self.shelf_menu is not None:
            self.shelf_menu.remove()
            self.shelf_menu = None

        if self.controller_ui is not None:
            self.controller_ui.close()
            self.controller_ui = None

menu = PluginMenu()
def initializePlugin(mobject):
    if om.MGlobal.mayaState() != om.MGlobal.kInteractive:
        return

    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

