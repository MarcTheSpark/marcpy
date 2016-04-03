__author__ = 'mpevans'


__author__ = 'mpevans'

import time
import bisect

from marcpy.marqt.marc_paint import *
from marcpy.marqt.dialogs import do_var_setter_dialog
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QColorDialog, QListWidget, QAbstractItemView, QListWidgetItem,QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QSpinBox,\
    QDoubleSpinBox, QLineEdit, QComboBox, QLabel, QPushButton
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
import random
from marcpy.marqt.animations import get_text_fade_animation
import functools

from marcpy.utilities import *

from marcpy.parameters.discrete_sequence import DiscreteSequence


class DiscreteSequenceEditor(MarcPaintWidget):

    def __init__(self, discrete_sequences, color_dictionary=None, window_size=(700, 400), sequence_name="sequence",
                 current_file=None, clipboard_memory_length=10, short_cut_order=None):
        super(DiscreteSequenceEditor, self).__init__(window_size=window_size, bg_color=(1.0, 1.0, 1.0, 1.0), parent=None,
                                              title="Editing " + sequence_name)

        assert hasattr(discrete_sequences, "__len__")

        first_entry_time = float("inf")
        last_entry_time = float("-inf")

        self.color_dictionary = {} if color_dictionary is None else color_dictionary
        self.short_cut_order = [] if short_cut_order is None else short_cut_order

        for ds in discrete_sequences:
            assert isinstance(ds, DiscreteSequence)
            if ds.get_last_entry_time() is not None and ds.get_last_entry_time() > last_entry_time:
                last_entry_time = ds.get_last_entry_time()
            if ds.get_first_entry_time() is not None and ds.get_first_entry_time() < first_entry_time:
                first_entry_time = ds.get_first_entry_time()
            for val in ds.data.values():
                if val not in self.color_dictionary:
                    self.color_dictionary[val] = (random.random(), random.random(), random.random())
                if val not in self.short_cut_order:
                    self.short_cut_order.append(val)
            if ds.default_value is not None and ds.default_value not in self.color_dictionary:
                self.color_dictionary[ds.default_value] = (random.random(), random.random(), random.random())
                self.short_cut_order.append(val)
            if None not in self.color_dictionary:
                self.color_dictionary[None] = (1, 1, 1)

        if first_entry_time == float("inf") and last_entry_time == float("-inf"):
            first_entry_time = 0
            last_entry_time = 10
        elif first_entry_time == float("inf"):
            if last_entry_time == 0:
                first_entry_time = -10
            elif last_entry_time > 0:
                first_entry_time = -last_entry_time
            else:
                first_entry_time = 2*last_entry_time
        elif last_entry_time == float("-inf"):
            if first_entry_time == 0:
                last_entry_time = 10
            elif first_entry_time < 0:
                last_entry_time = -first_entry_time
            else:
                first_entry_time = 2*last_entry_time

        time_width = last_entry_time - first_entry_time
        self.set_view_bounds(min(first_entry_time, 0), last_entry_time + time_width/7, 0.0, 1.0)
        self.sequence_name = sequence_name
        self.set_resize_mode(ResizeModes.STRETCH)
        self.discrete_sequences = discrete_sequences
        self.current_file = current_file

        self.selected_handles = []
        self.last_drag = None

        self.new_data_start = None
        self.new_data_end = None

        self.current_value_painted = 0
        self.digits_typed = []

        self.shift_down = False
        self.start_animation(0.02)

    def animate(self, dt):
        self.clear()
        self.draw_sequences()
        if self.new_data_start is not None:
            self.draw_new_data()
        self.draw_sequence_dividers()

    def draw_sequences(self):
        for which_sequence, ds in enumerate(self.discrete_sequences):
            assert isinstance(ds, DiscreteSequence)
            self.fill_rects((self.view_bounds[0],
                             self.get_view_height() - (float(which_sequence+1) / len(self.discrete_sequences))),
                            (self.get_view_width(),
                             float(self.get_view_height())/len(self.discrete_sequences)),
                            self.color_dictionary[ds.default_value])

            if len(ds) > 0:
                ds.sort_data()

                for which_datum in range(len(ds.sorted_data)):
                    if which_datum == len(ds.sorted_data) - 1:
                        start_time, val = ds.sorted_data[which_datum]
                        end_time = self.view_bounds[1]
                    else:
                        start_time, val = ds.sorted_data[which_datum]
                        end_time = ds.sorted_data[which_datum+1][0]
                    self.fill_rects((start_time,
                                     self.get_view_height()-(float(which_sequence+1)/len(self.discrete_sequences))),
                                    (end_time - start_time, float(self.get_view_height())/len(self.discrete_sequences)),
                                    self.color_dictionary[val])
                    edge_width = 0.002 * self.get_view_width()
                    for handle in self.selected_handles:
                        if handle.index == which_datum and handle.discrete_sequence == ds:
                            edge_width = 0.005 * self.get_view_width()
                    self.draw_lines(((start_time, self.get_view_height()-float(which_sequence+1)/len(self.discrete_sequences)),
                                     (start_time, self.get_view_height()-float(which_sequence)/len(self.discrete_sequences))),
                                    (0, 0, 0), width=edge_width)

    def draw_sequence_dividers(self):
        for which_sequence, ds in enumerate(self.discrete_sequences):
            if which_sequence != len(self.discrete_sequences) - 1:
                self.draw_lines(((self.view_bounds[0],
                                 self.get_view_height() - float(which_sequence+1) / len(self.discrete_sequences)),
                                 (self.view_bounds[1],
                                 self.get_view_height() - float(which_sequence+1) / len(self.discrete_sequences))),
                                (0, 0, 0), width=0.007)

    def draw_new_data(self):
        edge_width = 0.002 * self.get_view_width()
        min_sequence = min(self.new_data_start[0], self.new_data_end[0])
        max_sequence = max(self.new_data_start[0], self.new_data_end[0])
        start_time, end_time = self.new_data_start[1], self.new_data_end[1]
        low_y = self.get_view_height()-(float(max_sequence+1)/len(self.discrete_sequences))
        high_y = self.get_view_height()-(float(min_sequence)/len(self.discrete_sequences))
        self.fill_rects((start_time, low_y),
                        (end_time - start_time, high_y-low_y),
                        self.color_dictionary[self.short_cut_order[self.current_value_painted-1]])
        self.draw_lines(((start_time, low_y),
                        (start_time, high_y)),
                        (0, 0, 0), width=edge_width)
        self.draw_lines(((end_time, low_y),
                        (end_time, high_y)),
                        (0, 0, 0), width=edge_width)

    def get_handles_at_position(self, x, y):
        discrete_sequence, closest_index = self.get_nearest_data_point(x, y)
        if closest_index is None:
            return None

        temporal_width = self.view_bounds[1] - self.view_bounds[0]
        if abs(discrete_sequence.time_entries[closest_index] - x) < temporal_width / 100:
            return Handle(discrete_sequence, closest_index),
        else:
            if x < discrete_sequence.time_entries[closest_index]:
                if closest_index == 0:
                    return None
                else:
                    return Handle(discrete_sequence, closest_index-1), Handle(discrete_sequence, closest_index)
            else:
                if closest_index == len(discrete_sequence) - 1:
                    return None
                else:
                    return Handle(discrete_sequence, closest_index), Handle(discrete_sequence, closest_index+1)

    def get_nearest_data_point(self, x, y):
        which_sequence = self.get_sequence_at_y_coord(y)
        discrete_sequence = self.discrete_sequences[which_sequence]
        assert isinstance(discrete_sequence, DiscreteSequence)
        if len(discrete_sequence) == 0:
            return discrete_sequence, None
        discrete_sequence.sort_data()
        closest_index = get_closest_index(discrete_sequence.time_entries, x)
        return discrete_sequence, closest_index

    def get_sequence_at_y_coord(self, y_coord):
        return len(self.discrete_sequences) - int(y_coord*len(self.discrete_sequences)) - 1

    def transmit_sorted_data_to_dict_data(self):
        # after moving something, we translate the data to the dictionary
        for discrete_sequence in self.discrete_sequences:
            assert isinstance(discrete_sequence, DiscreteSequence)
            if len(discrete_sequence) > 0:
                discrete_sequence.data = {}
                for t, val in reversed(discrete_sequence.sorted_data):
                    if t not in discrete_sequence.data:
                        discrete_sequence.data[t] = val
                discrete_sequence.sorted_data = None
                discrete_sequence.sort_data()

    def on_mouse_down(self, (x, y), buttons_and_modifiers):
        if self.current_value_painted == 0:
            handles_touched = self.get_handles_at_position(x, y)

            if handles_touched is not None:
                all_touched_handles_in_selected_handles = True
                for ht in handles_touched:
                    if ht not in self.selected_handles:
                        all_touched_handles_in_selected_handles = False
                        break

                # special case: if we have two adjacent handles selected then we want to clear the current handles
                # (unless shift is down) so that we can grab one or the other end separately.
                if len(self.selected_handles) == 2 \
                        and self.selected_handles[0].discrete_sequence == self.selected_handles[1].discrete_sequence \
                        and self.selected_handles[0].index + 1 == self.selected_handles[1].index:
                    all_touched_handles_in_selected_handles = False
            else:
                all_touched_handles_in_selected_handles = False

            # unless shift is down or all touched handles are part of the selection, clear the selected handles
            if not all_touched_handles_in_selected_handles and "shift" not in buttons_and_modifiers:
                self.selected_handles = []

            # add the touched handles to the selected handles
            if handles_touched is not None:
                for ht in handles_touched:
                    if ht not in self.selected_handles:
                        self.selected_handles.append(ht)

            self.last_drag = x, y
        else:
            self.new_data_start = self.get_sequence_at_y_coord(y), x
            self.new_data_end = self.get_sequence_at_y_coord(y), x

    def on_mouse_up(self, (x, y), buttons_and_modifiers):
        if self.current_value_painted == 0:
            self.transmit_sorted_data_to_dict_data()
            self.last_drag = None
        else:
            if self.new_data_start is not None and self.new_data_end is not None:
                self.finalize_new_data()
            self.new_data_start = None
            self.new_data_end = None

    def on_mouse_drag(self, (x, y), buttons_and_modifiers):
        if self.current_value_painted == 0:
            x_motion = x - self.last_drag[0]
            for handle in self.selected_handles:
                if x_motion > handle.room_to_the_right:
                    x_motion = handle.room_to_the_right
                    break
                elif x_motion < -handle.room_to_the_left:
                    x_motion = -handle.room_to_the_left
                    break
            for handle in self.selected_handles:
                handle.move(x_motion)
            self.last_drag = x, y
        else:
            self.new_data_end = self.get_sequence_at_y_coord(y), x

    def on_mouse_move(self, (x, y)):
        # self.current_index = self.get_index_at_x_coord(x)
        # self.current_height = self.get_value_at_y_coord(y)
        pass

    def on_mouse_scroll(self, delta_x, delta_y):
        if abs(delta_x) > abs(delta_y):
            # mostly horizontal motion, so we scroll
            # 300 is a fairly average scroll value, and a swipe will tend to output many values before finishing,
            # adding up to about 10 times that, i.e. 3000. Let's have an average scroll go about half of the distance
            # between left and right. So:
            lr_shift = - delta_x/3000.0 * self.get_view_width() / 2  # for some reason x is reversed
            self.set_view_bounds(self.view_bounds[0] + lr_shift, self.view_bounds[1] + lr_shift,
                                 self.view_bounds[2], self.view_bounds[3])
        else:
            # mostly vertical motion, so we zoom
            # since zoom is a multiplication
            zoom_factor = 2.0 ** (delta_y/3000.0)
            expansion_amount = self.get_view_width()*(1-zoom_factor)
            self.set_view_bounds(self.view_bounds[0] - expansion_amount/2, self.view_bounds[1] + expansion_amount/2,
                                 self.view_bounds[2], self.view_bounds[3])

    def on_key_press(self, key, modifiers):
        if key == 69 and "meta" in modifiers:
            # command-e edits the values and their representative colors
            ve = ValuesEditor(self.color_dictionary, self.short_cut_order, [ds.default_value for ds in self.discrete_sequences])
            value_dialog_result = ve.do_dialog()
            if value_dialog_result is None:
                return
            old_to_new_values, self.color_dictionary, self.short_cut_order = value_dialog_result

            for ds in self.discrete_sequences:
                # trigger a re-sorting to incorporate the new data dictionary into the sorted_data used for drawing
                ds.sorted_data = None

                for key in ds.data.keys():
                    value = ds.data[key]
                    if old_to_new_values[value] is None:
                        del ds.data[key]
                    else:
                        ds.data[key] = old_to_new_values[value]
        if 48 <= key <= 57:
            # number key from 0 to 9
            if "alt" in modifiers:
                self.digits_typed.append(str(key-48))
            else:
                self.switch_to_value_painted(key-48)
        if key == Qt.Key_Backspace:
            for handle in self.selected_handles:
                handle.delete_me()
            self.selected_handles = []

    def on_key_release(self, key, modifiers):
        if 'alt' not in modifiers and len(self.digits_typed) > 0:
            self.switch_to_value_painted(int(''.join(self.digits_typed)))
            self.digits_typed = []

    def switch_to_value_painted(self, value_to_paint):
        if value_to_paint-1 < len(self.short_cut_order):
            self.current_value_painted = value_to_paint

            location = (self.view_bounds[0] + self.view_bounds[1])/2, 0.9
            text_size = self.get_view_width()*0.2, 0.1
            rect_size = self.get_view_width()*0.25, 0.12
            fade_in_time, hold_time, fade_out_time = 0.2, 0.1, 0.4
            if self.current_value_painted != 0:
                text = str(self.short_cut_order[self.current_value_painted-1])
                rect_color = self.color_dictionary[self.short_cut_order[self.current_value_painted-1]]
            else:
                text = "Manipulate"
                rect_color = (1, 1, 1)

            text_color = (0, 0, 0) if get_luminance(*rect_color) > 0.3 else (1, 1, 1)

            def the_animation(dt, time_elapsed):
                max_alpha = 1.0

                duration = fade_in_time + hold_time + fade_out_time

                if time_elapsed > duration:
                    return False
                elif time_elapsed > fade_in_time + hold_time:
                    # fading out
                    alpha = max_alpha*(1-(time_elapsed-fade_in_time-hold_time)/fade_out_time)
                    self.fill_rects(location, rect_size, rect_color+(alpha, ), center_anchored=True)
                    self.draw_rects(location, rect_size, (0, 0, 0) + (alpha, ), center_anchored=True)
                    self.draw_text(text, location, text_size, text_color+(alpha, ), "Helvetica",
                                   anchor_type=TextAnchorType.ANCHOR_CENTER)
                elif time_elapsed > fade_in_time:
                    # holding
                    self.fill_rects(location, rect_size, rect_color, center_anchored=True)
                    self.draw_rects(location, rect_size, (0, 0, 0), center_anchored=True)
                    self.draw_text(text, location, text_size, text_color, "Helvetica",
                                   anchor_type=TextAnchorType.ANCHOR_CENTER)
                else:
                    # fading in
                    alpha = max_alpha*(time_elapsed/fade_in_time)
                    self.fill_rects(location, rect_size, rect_color+(alpha, ), center_anchored=True)
                    self.draw_rects(location, rect_size, (0, 0, 0) + (alpha, ), center_anchored=True)
                    self.draw_text(text, location, text_size, text_color+(alpha, ), "Helvetica",
                                   anchor_type=TextAnchorType.ANCHOR_CENTER)
                return True

            self.add_animation_layer(the_animation)

    def finalize_new_data(self):
        min_sequence = min(self.new_data_start[0], self.new_data_end[0])
        max_sequence = max(self.new_data_start[0], self.new_data_end[0])
        start_time = min(self.new_data_start[1], self.new_data_end[1])
        end_time = max(self.new_data_start[1], self.new_data_end[1])

        for i in range(min_sequence, max_sequence+1):
            ds = self.discrete_sequences[i]
            assert isinstance(ds, DiscreteSequence)
            if abs(start_time-end_time) < self.get_view_width()/300:
                # just adding a point
                ds.data[start_time] = self.short_cut_order[self.current_value_painted-1]
                ds.sorted_data = None
            else:
                end_value = ds.get_value_at_time(end_time)
                keys_to_delete = []
                for key in ds.data.keys():
                    if start_time <= key <= end_time:
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    del ds.data[key]
                ds.data[start_time] = self.short_cut_order[self.current_value_painted-1]
                ds.data[end_time] = end_value
                ds.sorted_data = None



class Handle:
    def __init__(self, discrete_sequence, index):
        assert isinstance(discrete_sequence, DiscreteSequence)
        self.discrete_sequence = discrete_sequence
        self.index = index
        self.current_time = discrete_sequence.time_entries[index]
        self.room_to_the_right = float("inf") if self.index == len(self.discrete_sequence.time_entries) - 1 else \
            self.discrete_sequence.time_entries[self.index + 1] - self.discrete_sequence.time_entries[self.index]
        self.room_to_the_left = float("inf") if self.index == 0 else \
            self.discrete_sequence.time_entries[self.index] - self.discrete_sequence.time_entries[self.index - 1]

    def move(self, delta_t):
        self.discrete_sequence.time_entries[self.index] += delta_t
        self.discrete_sequence.sorted_data[self.index] = self.discrete_sequence.sorted_data[self.index][0] + delta_t, \
                                                         self.discrete_sequence.sorted_data[self.index][1]
        self.room_to_the_right = float("inf") if self.index == len(self.discrete_sequence.time_entries) - 1 else \
            self.discrete_sequence.time_entries[self.index + 1] - self.discrete_sequence.time_entries[self.index]
        self.room_to_the_left = float("inf") if self.index == 0 else \
            self.discrete_sequence.time_entries[self.index] - self.discrete_sequence.time_entries[self.index - 1]
        self.current_time += delta_t

    def delete_me(self):
        del self.discrete_sequence.data[self.current_time]
        self.discrete_sequence.sorted_data = None

    def __str__(self):
        t, val = self.discrete_sequence.sorted_data[self.index]
        return "<Handle: " + str(t) + ", " + str(val) + ">"

    def __eq__(self, other):
        return self.index == other.index and self.discrete_sequence == other.discrete_sequence

class ValuesEditor(QDialog):

    def __init__(self, color_dictionary, short_cut_order, default_values, title="Available Values:", parent=None):
        super(ValuesEditor, self).__init__(parent)

        # color dictionary is values : colors
        # short_cut order is a list of values in order
        # To not lose track, we keep a dictionary mapping original value to resultant value, resultant color

        self.old_to_new_values = {value: value for value in color_dictionary.keys()}

        self.setWindowTitle(title)

        self.setMouseTracking(True)

        layout = QVBoxLayout(self)

        self.qlw = NumberedQListWidget()

        self.color_dictionary = color_dictionary

        for value in short_cut_order:
            item = NumberedQListWidgetItem(str(value), self.qlw)
            r, g, b = color_dictionary[value]
            item.setBackground(QColor(int(r*255), int(g*255), int(b*255)))
            if get_luminance(r, g, b) < 0.4:
                item.setForeground(QColor(255, 255, 255))
            item.object = value

        self.qlw.setDragDropMode(QAbstractItemView.InternalMove)
        layout.addWidget(self.qlw)

        def item_double_clicked(item):
            edit_value_result = do_var_setter_dialog([
                {
                    "description": "Value:",
                    "type": "string",
                    "max width": 80
                },
                {
                    "description": "Color:",
                    "type": "color"
                }
            ], [item.text(), item.background().color()], title="Edit Value:")

            if edit_value_result is None:
                return

            value_string, bg_color = edit_value_result
            if value_string != item.text():
                item.setText(value_string)
                try:
                    new_object = eval(value_string)
                except NameError:
                    new_object = value_string
                if item.object in self.old_to_new_values:
                    self.old_to_new_values[item.object] = new_object
                item.object = new_object


            item.setBackground(bg_color)
            r, g, b = bg_color.red()/255.0, bg_color.green()/255.0, bg_color.blue()/255.0
            if get_luminance(r, g, b) < 0.4:
                item.setForeground(QColor(255, 255, 255))

        self.qlw.itemDoubleClicked.connect(item_double_clicked)

        plus_minus_buttons = QHBoxLayout()
        plus_button = QPushButton("+")
        minus_button = QPushButton("-")
        plus_minus_buttons.addWidget(plus_button)
        plus_minus_buttons.addWidget(minus_button)
        layout.addLayout(plus_minus_buttons)

        def plus_clicked():
            new_value_result = do_var_setter_dialog([
                {
                    "description": "Value:",
                    "type": "string",
                    "max width": 80
                },
                {
                    "description": "Color:",
                    "type": "color"
                }
            ], ["", QColor(0, 0, 0)], title="New Value:")
            if new_value_result is None:
                return

            value_string, bg_color = new_value_result

            item = NumberedQListWidgetItem(value_string)
            try:
                item.object = eval(value_string)
            except NameError:
                item.object = value_string
            item.setBackground(bg_color)
            r, g, b = bg_color.red()/255.0, bg_color.green()/255.0, bg_color.blue()/255.0
            if get_luminance(r, g, b) < 0.4:
                item.setForeground(QColor(255, 255, 255))
            self.qlw.addItem(item)

        plus_button.clicked.connect(plus_clicked)

        def minus_clicked():
            if self.qlw.currentItem().object in self.old_to_new_values:
                self.old_to_new_values[self.qlw.currentItem().object] = None
            self.qlw.takeItem(self.qlw.currentRow())

        minus_button.clicked.connect(minus_clicked)

        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self
        )
        layout.addWidget(self.buttons)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def do_dialog(self):
        result = self.exec_()
        if result == QDialog.Accepted:
            # return an old value to new value dictionary, a color dictionary, and a shortcut list
            # if an old value gets mapped to None, it means it has been deleted, so each data point with that
            # value should be deleted.
            new_color_dictionary = {}
            new_short_cut_order = []
            for i in range(self.qlw.count()):
                this_item = self.qlw.item(i)
                new_color_dictionary[this_item.object] = (
                    this_item.background().color().red()/255.0,
                    this_item.background().color().green()/255.0,
                    this_item.background().color().blue()/255.0
                )
                new_short_cut_order.append(this_item.object)
            new_color_dictionary[None] = self.color_dictionary[None]
            return self.old_to_new_values, new_color_dictionary, new_short_cut_order
        else:
            return None


class NumberedQListWidgetItem(QListWidgetItem):
    def __init__(self, *args, **kwargs):
        QListWidgetItem.__init__(self, *args, **kwargs)
        self.number = None

    def text(self):
        # this is necessary to override because otherwise it seems like NumberedQListWidgetItem.data(0) gets called
        # resulting in getting the number along with the text
        return QListWidgetItem.data(self, 0)

    def data(self, role):
        x = QListWidgetItem.data(self, role)
        if role == 0:
            return str(self.number) + ". " + x
        else:
            return x


class NumberedQListWidget(QListWidget):
    def __init__(self, *args, **kwargs):
        QListWidget.__init__(self, *args, **kwargs)

    def paintEvent(self, e):
        for i in range(self.count()):
            self.item(i).number = i + 1
        super(NumberedQListWidget, self).paintEvent(e)


def edit_discrete_sequences(discrete_sequences, app=None):
    app = QtWidgets.QApplication(["Discrete Sequence Editor"])
    ds_editor = DiscreteSequenceEditor(discrete_sequences)
    ds_editor.show()
    ds_editor.raise_()
    app.exec_()
    return ds_editor.discrete_sequences

def edit_new_discrete_sequences(param_names, default_values=None):
    new_sequences = []
    for i, name in enumerate(param_names):
        new_sequences.append(DiscreteSequence(name, default_values[i] if default_values is not None else None))
    edit_discrete_sequences(new_sequences)