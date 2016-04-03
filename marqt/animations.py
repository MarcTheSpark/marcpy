__author__ = 'mpevans'

from marc_paint import *


def get_text_fade_animation(mp_widget, (fade_in_time, hold_time, fade_out_time),
                            text, (x, y), size, color, font_name, anchor_type=None):
    assert isinstance(mp_widget, MarcPaintWidget)

    color_rgb = color[0:3]
    if len(color) > 3:
        max_alpha = float(color[3])
    else:
        max_alpha = 1.0

    duration = fade_in_time + hold_time + fade_out_time

    def text_fade_animation(dt, time_elapsed):
        if time_elapsed > duration:
            return False
        elif time_elapsed > fade_in_time + hold_time:
            # fading out
            alpha = max_alpha*(1-(time_elapsed-fade_in_time-hold_time)/fade_out_time)
            mp_widget.draw_text(text, (x, y), size, color_rgb+(alpha, ), font_name, anchor_type=anchor_type)
        elif time_elapsed > fade_in_time:
            # holding
            mp_widget.draw_text(text, (x, y), size, color, font_name, anchor_type=anchor_type)
        else:
            # fading in
            alpha = max_alpha*(time_elapsed/fade_in_time)
            mp_widget.draw_text(text, (x, y), size, color_rgb+(alpha, ), font_name, anchor_type=anchor_type)
        return True

    return text_fade_animation