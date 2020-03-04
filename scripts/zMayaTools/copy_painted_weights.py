from pymel import core as pm
from maya import OpenMaya as om
from maya import cmds
import os, sys, time
try:
    from importlib import reload
except ImportError:
    pass
from zMayaTools import kdtree, maya_helpers, maya_logging
reload(maya_helpers)

from zMayaTools.ui import painted_weights_ui
reload(painted_weights_ui)

log = maya_logging.get_log()

class UI(maya_helpers.OptionsBox):
    title = 'Copy Painted Weights'

    def __init__(self):
        super(UI, self).__init__()

    def options_box_setup(self):
        self.optvars.add('zMirrorPaintedWeightsSurfaceAssociation', 'int', 1) # default to closest point

        self.option_box = pm.columnLayout(adjustableColumn=1)
        parent = self.option_box

        def deformer_node_changed(refresh):
            assert refresh in ('Input', 'Output')
            if refresh == 'Input':
                deformer_list = self.input_deformer_list
                deformer_shape_list = self.input_shape_list
                blend_shape_list = self.input_blend_shape_target_list
            else:
                deformer_list = self.output_deformer_list
                deformer_shape_list = self.output_shape_list
                blend_shape_list = self.output_blend_shape_target_list

            # Refresh the deformer's shape list.
            deformer_shape_list.refresh()

            # Refresh the blend shape target list.
            deformer = deformer_list.get_selected_deformer()
            blend_shape_list.refresh(deformer)

            self.refresh_enabled_blend_shape_target_list(blend_shape_list, deformer)
            if refresh == 'Input':
                self.refresh_enabled_blend_shape_target_list(self.output_blend_shape_target_list, self.output_deformer_list.get_selected_deformer())
            else:
                self.refresh_enabled_blend_shape_all()

        def input_blend_shape_changed():
            # When the input blend shape target is changed, refresh whether the output blend shape
            # target is enabled.  We disable the output target when the input is set to "all", since
            # it has no effect.
            deformer = self.output_deformer_list.get_selected_deformer()
            self.refresh_enabled_blend_shape_target_list(self.output_blend_shape_target_list, deformer)

        pm.optionMenuGrp('cpwInputDeformerList', label='Source deformer:', cc=lambda unused: deformer_node_changed('Input'))
        self.input_deformer_list = painted_weights_ui.DeformerList('cpwInputDeformerList')
        
        pm.optionMenuGrp('cpwInputShapeList', label='Shape:')
        self.input_shape_list = painted_weights_ui.DeformerShapeList('cpwInputShapeList', self.input_deformer_list)

        pm.optionMenuGrp('cpwInputBlendShapeTargets', label='Blend shape target:', cc=lambda unused: input_blend_shape_changed())
        self.input_blend_shape_target_list = painted_weights_ui.BlendShapeTargetList('cpwInputBlendShapeTargets', self.input_deformer_list)
        self.input_blend_shape_target_list.set_all_text('All (match by name)')

        pm.separator()

        pm.optionMenuGrp('cpwOutputDeformerList', label='Target deformer:', cc=lambda unused: deformer_node_changed('Output'))
        self.output_deformer_list = painted_weights_ui.DeformerList('cpwOutputDeformerList')

        pm.optionMenuGrp('cpwOutputShapeList', label='Shape:')
        self.output_shape_list = painted_weights_ui.DeformerShapeList('cpwOutputShapeList', self.output_deformer_list)

        pm.optionMenuGrp('cpwOutputBlendShapeTargets', label='Blend shape target:')
        self.output_blend_shape_target_list = painted_weights_ui.BlendShapeTargetList('cpwOutputBlendShapeTargets', self.output_deformer_list)

        pm.separator()

        pm.radioButtonGrp('mpwSurfaceAssociation1',
                select=True,
                numberOfRadioButtons=1,
                label='Surface Association:',
                label1='Closest point on surface')

        pm.radioButtonGrp('mpwSurfaceAssociation2',
                numberOfRadioButtons=1,
                label1='Ray cast',
                shareCollection='mpwSurfaceAssociation1')

        pm.radioButtonGrp('mpwSurfaceAssociation3',
                numberOfRadioButtons=1,
                label1='Closest component',
                shareCollection='mpwSurfaceAssociation1')

        pm.radioButtonGrp('mpwSurfaceAssociation4',
                numberOfRadioButtons=1,
                label1='UV space',
                shareCollection='mpwSurfaceAssociation1')

        pm.separator()

        # Populate fields.
        deformer_nodes = pm.ls(type=['wire', 'blendShape', 'weightGeometryFilter', 'skinCluster'])
        for node in deformer_nodes:
            pm.menuItem(parent='cpwInputDeformerList|OptionMenu', label=node)
            pm.menuItem(parent='cpwOutputDeformerList|OptionMenu', label=node)

        deformer_node_changed('Input')
        deformer_node_changed('Output')

    def _get_selected_deformer(self, which):
        assert which in ('Input', 'Output')
        if which == 'Input':
            return self.input_deformer_list.get_selected_deformer()
        else:
            return self.output_deformer_list.get_selected_deformer()

    def option_box_save(self):
        self.optvars['zMirrorPaintedWeightsSurfaceAssociation'] = self.get_selected_surface_association_idx()

    def option_box_load(self):
        pm.radioButtonGrp('mpwSurfaceAssociation%i' % self.optvars['zMirrorPaintedWeightsSurfaceAssociation'], e=True, select=True)
        
    def refresh_enabled_blend_shape_all(self):
        """
        Enable "All" in the source blend shape target list if the target is also a blendShape.
        
        We don't need to handle if the source itself is a blendShape, since the whole control
        will be disabled in that case.
        """
        output_deformer = self.output_deformer_list.get_selected_deformer()
        output_is_blend_shape = isinstance(output_deformer, pm.nodetypes.BlendShape)
        self.input_blend_shape_target_list.enable_all(output_is_blend_shape)

    def refresh_enabled_blend_shape_target_list(self, blend_shape_target_list, deformer):
        # Only enable this for blendShape deformers.
        enable_list = isinstance(deformer, pm.nodetypes.BlendShape)

        if blend_shape_target_list.control_name == 'cpwOutputBlendShapeTargets':
            # If this is the output deformer's list, and the input deformer is a blendShape and set to
            # All, disable this.
            input_deformer = self.input_deformer_list.get_selected_deformer()
            if isinstance(input_deformer, pm.nodetypes.BlendShape):
                selected_input_target = self.input_blend_shape_target_list.get_selected_target()
                if selected_input_target == '(all)':
                    enable_list = False

        pm.optionMenuGrp(blend_shape_target_list.control_name, edit=True, enable=enable_list)
    
    def option_box_apply(self):
        pm.setParent(self.option_box)

        input_deformer = self.input_deformer_list.get_selected_deformer()
        input_shape, _ = self.input_shape_list.get_selected_shape()

        output_deformer = self.output_deformer_list.get_selected_deformer()
        output_shape, _ = self.output_shape_list.get_selected_shape()

        # Find the selected surface association mode, and map it to a copySkinWeights argument.
        surface_association = self.get_selected_surface_association_idx()
        surface_association_modes = {
            1: 'closestPoint',
            2: 'rayCast',
            3: 'closestComponent',
            4: 'uvSpace',
        }
        surface_association = surface_association_modes[surface_association]

        # Duplicate the input and output shapes.
        input_shape_copy = pm.duplicate(input_shape)[0].getShape()
        output_shape_copy = pm.duplicate(output_shape)[0].getShape()

        # Create a temporary joint, and skin both shapes to it.  Disable weight normalization,
        # or weights will get forced to 1 since we only have one joint.
        temporary_joint = pm.createNode('joint')
        input_shape_skin = pm.skinCluster([input_shape_copy, temporary_joint], removeUnusedInfluence=False, normalizeWeights=False)
        output_shape_skin = pm.skinCluster([output_shape_copy, temporary_joint], removeUnusedInfluence=False, normalizeWeights=False)
       
        # Disable the skinClusters.  We're using them to transfer data, and we don't want them
        # to influence the temporary meshes.
        input_shape_skin.attr('envelope').set(0)
        output_shape_skin.attr('envelope').set(0)

        try:
            # Figure out which attributes to copy where.
            attrs_to_map = self.get_selected_attrs()

            # Do the copy.
            for src_attr, dst_attr in attrs_to_map:
                if not maya_helpers.copy_weights_to_skincluster(src_attr, input_shape_skin, input_shape_copy):
                    log.warning('Input has no deformer weights: %s', src_attr)
                    continue

                copy_options = {
                    'sourceSkin': input_shape_skin,
                    'destinationSkin': output_shape_skin,
                    'noMirror': True,

                    # Always use one-to-one joint association, since we're always copying the
                    # two temporary joints.
                    'influenceAssociation': 'oneToOne',
                }

                # If we're in UV space mode, find a UV set to copy.  Otherwise, set the association
                # mode.
                if surface_association == 'uvSpace':
                    # Use the current UV set for each mesh.
                    def get_current_uv_set(shape):
                        uv_sets = pm.polyUVSet(shape, q=True, currentUVSet=True)
                        if uv_sets:
                            return uv_sets[0]
                        else:
                            return 'map1'

                    input_shape_uv_set = get_current_uv_set(input_shape)
                    output_shape_uv_set = get_current_uv_set(output_shape)
                    copy_options['uvSpace'] = (input_shape_uv_set, output_shape_uv_set)
                else:
                    copy_options['surfaceAssociation'] = surface_association

                pm.copySkinWeights(**copy_options)
     
                # Read the copied weights out of the skinCluster and copy them to the output attribute.
                copied_weights = list(output_shape_skin.getWeights(output_shape_copy, 0))

                dst_weight_path = str(dst_attr)
                for index, value in enumerate(copied_weights):
                    cmds.setAttr('%s[%i]' % (dst_weight_path, index), value)
        finally:
            # Clean up our temporary nodes.
            pm.delete(input_shape_copy.getTransform())
            pm.delete(output_shape_copy.getTransform())
            pm.delete(temporary_joint)

        log.info( 'Copied %i %s' % (len(attrs_to_map), 'map' if len(attrs_to_map) == 1 else 'maps'))

    def get_selected_attrs(self):
        """
        Get the selected attributes to copy, returning a list of [(input, output)] tuples.

        For most deformers, this is just the painted weight attribute.  If we're copying multiple
        blend shapes because the source is set to "All", there can be more than one.
        """
        input_deformer = self.input_deformer_list.get_selected_deformer()
        _, input_deformer_shape_idx = self.input_shape_list.get_selected_shape()

        output_deformer = self.output_deformer_list.get_selected_deformer()
        _, output_deformer_shape_idx = self.output_shape_list.get_selected_shape()

        # Get the selection from the blend shape target dropdowns.  selected_input_target can
        # be '(all)' only if both deformers are blendShapes.
        selected_input_target = self.input_blend_shape_target_list.get_selected_target()
        selected_output_target = self.output_blend_shape_target_list.get_selected_target()

        if isinstance(input_deformer, pm.nodetypes.BlendShape) and selected_input_target == '(all)':
            assert isinstance(output_deformer, pm.nodetypes.BlendShape), 'Expected the output deformer to be a blendShape, found %s' % output_deformer.nodeType()

            input_blend_shape_targets = input_deformer.attr('weight')
            output_blend_shape_targets = output_deformer.attr('weight')

            # Loop over each available selection, and see if we should add it to the output.
            input_target = input_deformer.attr('it').elementByLogicalIndex(input_deformer_shape_idx)
            output_target = output_deformer.attr('it').elementByLogicalIndex(output_deformer_shape_idx)

            attrs_to_map = []

            # Add the main deformer weights.
            attrs_to_map.append((input_target.attr('bw'), output_target.attr('bw')))

            # Make a mapping of blend shape target names to target weights.  We'll use this to
            # match up the names.
            input_blend_shapes = {pm.aliasAttr(target, q=True): target for target in input_blend_shape_targets}
            output_blend_shapes = {pm.aliasAttr(target, q=True): target for target in output_blend_shape_targets}

            for input_name, input_blend_shape in input_blend_shapes.items():
                output_blend_shape = output_blend_shapes.get(input_name)
                if output_blend_shape is None:
                    log.warning('No matching blend shape found for: %s' % input_name)
                    continue

                log.debug('Mapped blend shape: %s' % (pm.aliasAttr(input_blend_shape, q=True)))
                input_target_group = input_target.attr('itg').elementByLogicalIndex(input_blend_shape.index())
                output_target_group = output_target.attr('itg').elementByLogicalIndex(output_blend_shape.index())
                input_weights = input_target_group.attr('targetWeights')
                output_weights = output_target_group.attr('targetWeights')
                attrs_to_map.append((input_weights, output_weights))

            return attrs_to_map

        def get_painted_attribute(deformer, selected_target, deformer_shape_idx):
            if isinstance(deformer, pm.nodetypes.BlendShape):
                input_target = deformer.attr('it').elementByLogicalIndex(deformer_shape_idx)
                if selected_target == '(main)':
                    # The first entry in the target list is the weights on the blendShape deformer
                    # itself, which is the first entry in the "Target" list in the blend shape painting
                    # tool.
                    return input_target.attr('bw')

                input_target_group = input_target.attr('itg').elementByLogicalIndex(selected_target.index())
                return input_target_group.attr('targetWeights')
                
            else:
                # Other things are weightGeometryFilters, eg. delta mush and tension deformers.
                # These only have a single paintable attribute.
                input_target = deformer.attr('weightList').elementByLogicalIndex(deformer_shape_idx)
                return input_target.attr('weights')

        input_attr = get_painted_attribute(input_deformer, selected_input_target, input_deformer_shape_idx)
        output_attr = get_painted_attribute(output_deformer, selected_output_target, output_deformer_shape_idx)
        return [(input_attr, output_attr)]

    def get_selected_surface_association_idx(self):
        for i in range(1,5):
            if pm.radioButtonGrp('mpwSurfaceAssociation%i' % i, q=True, select=True):
                return i

        return 1

