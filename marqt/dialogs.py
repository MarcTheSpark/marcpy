__author__ = 'mpevans'


from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QSpinBox,\
    QDoubleSpinBox, QLineEdit, QComboBox, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5 import QtWidgets
from widgets import ColorSwatchWidget


class VariableSetterDialog(QDialog):
    """
    An Example:

    i, f, s, c, cl = 42, 5.6, "bunny", "machine", (100, 200, 0)

    i, f, s, c, cl = do_var_setter_dialog([{"description": "An int:",
                                        "type": "int",
                                        "min": 20,
                                        "max": 60},
                                       {"description": "A float:",
                                        "type": "float",
                                        "min": -10,
                                        "max": 10,
                                        "step": 0.1,
                                        "decimals": 1},
                                       {"description": "A string:",
                                        "type": "string",
                                        "max width": 80},
                                       {"description": "A combo:",
                                        "type": "combo",
                                        "options": ["tiny", "banana", "machine"],
                                        "max width": 100},
                                        {"description": "A color:",
                                        "type": "color"}], [i, f, s, c, cl])
    print i, f, s, c, cl
    """

    def __init__(self, var_info, initial_values, title="Set Variables:", parent=None):
        super(VariableSetterDialog, self).__init__(parent)

        assert len(var_info) == len(initial_values)

        self.setWindowTitle(title)

        layout = QVBoxLayout(self)

        self.value_holders = []

        for i in range(len(var_info)):
            info_dictionary = var_info[i]
            assert isinstance(info_dictionary, dict)
            h_layout = QHBoxLayout()
            h_layout.addWidget(QLabel(info_dictionary["description"]))
            if info_dictionary["type"] == "int":
                spin_box = QSpinBox()
                spin_box.setMinimum(info_dictionary["min"])
                spin_box.setMaximum(info_dictionary["max"])
                if info_dictionary.has_key("step"):
                    spin_box.setSingleStep(info_dictionary["step"])
                if info_dictionary.has_key("max width"):
                    spin_box.setMaximumWidth(info_dictionary["max width"])
                spin_box.setValue(initial_values[i])
                self.value_holders.append(spin_box)
                h_layout.addWidget(spin_box)
                layout.addLayout(h_layout)
            elif info_dictionary["type"] == "float":
                spin_box = QDoubleSpinBox()
                spin_box.setMinimum(info_dictionary["min"])
                spin_box.setMaximum(info_dictionary["max"])
                if info_dictionary.has_key("step"):
                    spin_box.setSingleStep(info_dictionary["step"])
                if info_dictionary.has_key("decimals"):
                    spin_box.setDecimals(info_dictionary["decimals"])
                if info_dictionary.has_key("max width"):
                    spin_box.setMaximumWidth(info_dictionary["max width"])
                spin_box.setValue(initial_values[i])
                self.value_holders.append(spin_box)
                h_layout.addWidget(spin_box)
                layout.addLayout(h_layout)
            elif info_dictionary["type"] == "string":
                line_edit = QLineEdit()
                if info_dictionary.has_key("max length"):
                    line_edit.setMaxLength(info_dictionary["max length"])
                if info_dictionary.has_key("max width"):
                    line_edit.setMaximumWidth(info_dictionary["max width"])
                if info_dictionary.has_key("max width"):
                    line_edit.setMaximumWidth(info_dictionary["max width"])
                line_edit.setText(initial_values[i])
                line_edit.value = line_edit.text
                self.value_holders.append(line_edit)
                h_layout.addWidget(line_edit)
                layout.addLayout(h_layout)
            elif info_dictionary["type"] == "combo":
                combo_box = QComboBox()
                combo_box.addItems(info_dictionary["options"])

                if info_dictionary.has_key("max width"):
                    combo_box.setMaximumWidth(info_dictionary["max width"])
                combo_box.setCurrentText(initial_values[i])
                combo_box.value = combo_box.currentText
                self.value_holders.append(combo_box)
                h_layout.addWidget(combo_box)
                layout.addLayout(h_layout)
            elif info_dictionary["type"] == "color":
                swatch = ColorSwatchWidget(initial_values[i])
                self.value_holders.append(swatch)
                h_layout.addWidget(swatch)
                layout.addLayout(h_layout)

        # OK and Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        layout.addWidget(self.buttons)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def do_dialog(self):
        result = self.exec_()
        if result == QDialog.Accepted:
            out = []
            for value_holder in self.value_holders:
                out.append(value_holder.value())
            if len(out) == 1:
                return out[0]
            else:
                return tuple(out)
        else:
            return None


def do_var_setter_dialog(var_info, initial_values, title="Set Variables:"):
    variable_setter = VariableSetterDialog(var_info, initial_values, title)
    return variable_setter.do_dialog()