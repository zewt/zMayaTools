import pymel.core as pm
from zMayaTools import maya_helpers

def next_time_slider_frame(delta):
    """
    Change the current time by the given number of frames, staying within the time
    slider range.
    """
    min_frame = pm.playbackOptions(q=True, min=True)
    max_frame = pm.playbackOptions(q=True, max=True)
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

def setup_runtime_commands():
    maya_helpers.create_or_replace_runtime_command('NextFrameOnTimeSlider', category='zMayaTools.Animation',
            annotation='zMayaTools: Go to the next frame, staying on the time slider',
            command='from zMayaTools import animation_helpers; animation_helpers.next_time_slider_frame(+1)')
    maya_helpers.create_or_replace_runtime_command('PreviousFrameOnTimeSlider', category='zMayaTools.Animation',
            annotation='zMayaTools: Go to the previous frame, staying on the time slider',
            command='from zMayaTools import animation_helpers; animation_helpers.next_time_slider_frame(-1)')

