import pymel.core as pm
from zMayaTools import maya_helpers, preferences

optvars = maya_helpers.OptionVars()
optvars.add('zMayaToolsFrameStepIncludesNextFrame', 'bool', False)

def next_time_slider_frame(delta):
    """
    Change the current time by the given number of frames, staying within the time
    slider range.
    """
    min_frame = pm.playbackOptions(q=True, min=True)
    max_frame = pm.playbackOptions(q=True, max=True)

    if optvars['zMayaToolsFrameStepIncludesNextFrame']:
        max_frame += 1

    current_frame = pm.currentTime(q=True)
    if current_frame < min_frame or current_frame > max_frame:
        if delta < 0:
            new_frame = max_frame
        elif delta > 0:
            new_frame = min_frame
    else:
        new_frame = current_frame + delta
        new_frame -= min_frame
        new_frame %= max_frame - min_frame + 1
        new_frame += min_frame

    pm.currentTime(new_frame)

def go_to_first_time_slider_frame():
    """
    Go to the first frame on the time slider.

    This is the same as GoToMinFrame.  It's only here so if you're binding zLastFrameOnTimeSlider
    in the keyframe editor, you don't have to find GoToMinFrame separately.
    """
    min_frame = pm.playbackOptions(q=True, min=True)
    pm.currentTime(min_frame)

def go_to_last_time_slider_frame():
    """
    Go to the last frame on the time slider.

    This is the same as GoToMaxFrame, but supports the zMayaToolsFrameStepIncludesNextFrame
    option.
    """
    max_frame = pm.playbackOptions(q=True, max=True)
    if optvars['zMayaToolsFrameStepIncludesNextFrame']:
        max_frame += 1
    pm.currentTime(max_frame)

_preference_handler = None
def install():
    maya_helpers.create_or_replace_runtime_command('zNextFrameOnTimeSlider', category='zMayaTools.Animation',
            annotation='zMayaTools: Go to the next frame, staying on the time slider',
            command='from zMayaTools import animation_helpers; animation_helpers.next_time_slider_frame(+1)')
    maya_helpers.create_or_replace_runtime_command('zPreviousFrameOnTimeSlider', category='zMayaTools.Animation',
            annotation='zMayaTools: Go to the previous frame, staying on the time slider',
            command='from zMayaTools import animation_helpers; animation_helpers.next_time_slider_frame(-1)')
    maya_helpers.create_or_replace_runtime_command('zGoToMaxFrame', category='zMayaTools.Animation',
            annotation='zMayaTools: Go to the last frame on the time slider',
            command='from zMayaTools import animation_helpers; animation_helpers.go_to_last_time_slider_frame()')
    maya_helpers.create_or_replace_runtime_command('zGoToMinFrame', category='zMayaTools.Animation',
            annotation='zMayaTools: Go to the first frame on the time slider',
            command='from zMayaTools import animation_helpers; animation_helpers.go_to_first_time_slider_frame()')

    # Create our preferences window block.
    def create_prefs_widget(pref_handler):
        pm.checkBoxGrp('zmt_FrameStepIncludesNextFrame',
            numberOfCheckBoxes=1,
            label='',
            cw2=(140, 300),
            label1='Frame stepping includes the frame after the time slider range',
            cc1=pref_handler.get_change_callback('zMayaToolsFrameStepIncludesNextFrame'))

    global _preference_handler
    _preference_handler = preferences.PreferenceHandler('1_menus', create_prefs_widget)
    _preference_handler.add_option(optvars.get('zMayaToolsFrameStepIncludesNextFrame'), 'zmt_FrameStepIncludesNextFrame')
    _preference_handler.register()

def uninstall():
    if _preference_handler is not None:
        _preference_handler.unregister()

