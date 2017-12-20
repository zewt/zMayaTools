from pymel import core as pm
from maya import cmds
import os, sys, time
from zMayaTools import kdtree, maya_helpers, maya_logging, vertex_mapping

from zMayaTools.ui import painted_weights_ui
reload(painted_weights_ui)

log = maya_logging.get_log()

# This only supports deformed meshes, and not NURBS surfaces or curves.
# This only supports "closest component" matching, and should be used with cleanly mirrored meshes.
def copy_attribute_with_map(src_weights, dst_weights, index_mapping):
    # PyMel prints a "Could not create desired MFn" every time we read a weight.  To avoid spamming this thousands of times,
    # read all of the weights at once.  This is probably faster anyway.
    existing_src_indices = src_weights.getArrayIndices()
    existing_src_values = src_weights.get()
    existing_src_values = {index: value for index, value in zip(existing_src_indices, existing_src_values)}

    existing_dst_indices = dst_weights.getArrayIndices()
    existing_dst_values = dst_weights.get()
    existing_dst_values = {index: value for index, value in zip(existing_dst_indices, existing_dst_values)}

    new_values = {}
    for dst, src in index_mapping.items():
        # If there's no value in the source, don't create one at the destination.
        if src not in existing_src_values:
            continue
        value = existing_src_values.get(src)
        new_values[dst] = value

    # Set any indices that we're not going to set to 1.  This is silly.  How do you simply clear an array attribute?
    dst_weight_path = str(dst_weights)
    for existing_dst_index in existing_dst_values.keys():
        if existing_dst_index in new_values:
            continue

        # Use cmds to avoid "Could not create desired MFn" spam.
        cmds.setAttr('%s[%i]' % (dst_weight_path, existing_dst_index), 1)

    for index, value in new_values.items():
        cmds.setAttr('%s[%i]' % (dst_weight_path, index), value)

class UI(maya_helpers.OptionsBox):
    title = 'Copy Painted Weights'

    def __init__(self):
        super(UI, self).__init__()

    def options_box_setup(self):
        self.optvars.add('zMirrorPaintedWeightsThreshold', 'float', 0.02)

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

        pm.floatSliderGrp('cpwThreshold', label='Vertex matching threshold', field=True, v=0.01, min=0, max=.1, fieldMinValue=0, fieldMaxValue=1000)

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
        self.optvars['zMirrorPaintedWeightsThreshold'] = pm.floatSliderGrp('cpwThreshold', q=True, v=True)

    def option_box_load(self):
        pm.floatSliderGrp('cpwThreshold', edit=True, v=self.optvars['zMirrorPaintedWeightsThreshold'])
        
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

        threshold = pm.floatSliderGrp('cpwThreshold', q=True, v=True)

        # Map vertex indices from the source shape to the destination shape.
        index_mapping, unmapped_dst_vertices = vertex_mapping.make_vertex_map(input_shape, output_shape, threshold=0.01)

        if unmapped_dst_vertices:
            log.warning('Warning: unmapped vertices: %s', ' '.join(str(idx) for idx in unmapped_dst_vertices))
        if not index_mapping:
            log.error('No symmetric vertices were matched')
            return
            
        # Figure out which attributes to copy where.
        attrs_to_map = self.get_selected_attrs()

        # Do the copy.
        for src_attr, dst_attr in attrs_to_map:
            copy_attribute_with_map(src_attr, dst_attr, index_mapping)

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


