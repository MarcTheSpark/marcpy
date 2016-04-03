__author__ = 'mpevans'

from marcpy.marqt.marc_paint import *
from PyQt5 import QtWidgets
from marcpy.utilities import *
from marcpy.marqt.dialogs import do_var_setter_dialog

class OneDParamEditor(MarcPaintWidget):

    def __init__(self, array_data, data_range, window_size=(700, 400), param_name="parameter", current_file=None):
        super(OneDParamEditor, self).__init__(window_size=window_size, bg_color=(1.0, 1.0, 1.0, 1.0), parent=None,
                                              title="Editing " + param_name)
        self.param_name = param_name
        self.set_resize_mode(ResizeModes.STRETCH)
        self.set_view_bounds(0, float(window_size[0])/window_size[1], 0, 1.0)
        self.array_data = array_data
        self.data_range = data_range
        self.current_file = current_file

        self.last_drag = None
        self.current_index = None
        self.current_height = None

        self.index_range = (0, len(array_data)-1)

        self.start_animation(0.02)

    @classmethod
    def new_from_attributes(cls, length, data_range, default_value=None,
                            window_size=(700, 400), param_name="parameter"):
        assert isinstance(length, int)
        data_range = (float(data_range[0]), float(data_range[1]))
        if default_value is None:
            default_value = (data_range[0] + data_range[1]) / 2
        array_data = np.full(length, default_value)
        return cls(array_data, data_range, window_size=window_size, param_name=param_name)

    @classmethod
    def new_from_file(cls, file_path, window_size=(700, 400)):
        data, data_range, param_name = load_object(file_path)
        return cls(data, data_range, window_size=window_size, param_name=param_name, current_file=file_path)

    def animate(self, dt):
        self.clear()
        self.draw_array()
        self.draw_location()

    def draw_array(self):
        # figure out coordinates for drawing melodic line
        x_coordinates = np.linspace(0.0, self.get_view_width(), self.index_range[1] - self.index_range[0])
        y_coordinates = (self.array_data[self.index_range[0]:self.index_range[1]] - self.data_range[0]) / \
                        (self.data_range[1] - self.data_range[0])
        line_strip_coordinates = np.column_stack([x_coordinates, y_coordinates])
        self.draw_line_strip(line_strip_coordinates, (0, 0, 0), width=0.01)

    def draw_location(self):
        if self.current_index is not None:
            ci_string = str(self.current_index)
            while len(ci_string) < 3:
                ci_string = " " + ci_string
            self.draw_text(ci_string + ", " + format(self.current_height, '.3f'),
                           (self.get_view_width()*0.75, self.get_view_height()*0.9),
                           self.get_view_height()*0.08, (0.2, 0.2, 0.2), "Helvetica")

    def get_index_at_x_coord(self, x_coord):
        if x_coord < 0:
            return self.index_range[0]
        if x_coord >= self.get_view_width():
            return self.index_range[-1]
        return int(float(x_coord)/self.get_view_width()*(self.index_range[1] - self.index_range[0])) \
               + self.index_range[0]

    def get_value_at_y_coord(self, y_coord):
        value = float(y_coord)/self.get_view_height()*(self.data_range[1] - self.data_range[0]) + self.data_range[0]
        return min(max(value, self.data_range[0]), self.data_range[1])

    def on_mouse_down(self, (x, y), buttons):
        index = self.get_index_at_x_coord(x)
        self.array_data[index] = self.get_value_at_y_coord(y)
        self.last_drag = index

    def on_mouse_up(self, (x, y), buttons):
        pass

    def on_mouse_drag(self, (x, y), buttons):
        index = self.get_index_at_x_coord(x)
        if self.last_drag != index:
            lower = min(self.last_drag, index)
            upper = max(self.last_drag, index)
            for i in range(lower, upper+1):
                progress = abs(float(i - self.last_drag)) / (upper - lower)
                self.array_data[i] = progress*self.get_value_at_y_coord(y) + (1-progress)*self.array_data[self.last_drag]
        else:
            self.array_data[index] = self.get_value_at_y_coord(y)
        self.last_drag = index

    def on_mouse_move(self, (x, y)):
        self.current_index = self.get_index_at_x_coord(x)
        self.current_height = self.get_value_at_y_coord(y)

    def on_key_press(self, key, modifiers):
        if key == 83 and "meta" in modifiers:
            # command-s
            if self.current_file is not None and "shift" not in modifiers:
                save_object((self.array_data, self.data_range, self.param_name), self.current_file)
            else:
                path = os.path.dirname(__file__)
                filename = QtWidgets.QFileDialog.getSaveFileName(QtWidgets.QFileDialog(), 'Save Array', path)[0]
                save_object((self.array_data, self.data_range, self.param_name), filename)
        if key == 82 and "meta" in modifiers:
            # command-r changes range
            low, high = do_var_setter_dialog([{"description": "Low:",
                                               "type": "int",
                                               "min": 0,
                                               "max": len(self.array_data)},
                                              {"description": "High:",
                                               "type": "int",
                                               "min": 0,
                                               "max": len(self.array_data)}], [0, len(self.array_data)])
            if low < high:
                self.index_range = (low, high)


def edit_param_file(filename, window_size=(700, 400)):
    app = QtWidgets.QApplication(["Param Editor"])
    param_editor = OneDParamEditor.new_from_file(filename, window_size=window_size)
    param_editor.raise_()
    param_editor.show()
    app.exec_()

def edit_new_param(length, data_range, default_value=None, window_size=(700, 400), param_name="parameter"):
    app = QtWidgets.QApplication(["Param Editor"])
    param_editor = OneDParamEditor.new_from_attributes(length, data_range, default_value=default_value,
                                                       window_size=window_size, param_name=param_name)
    param_editor.raise_()
    param_editor.show()
    app.exec_()
