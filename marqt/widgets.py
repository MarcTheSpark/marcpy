__author__ = 'mpevans'

from PyQt5.QtWidgets import QColorDialog, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5 import QtWidgets


class ColorSwatchWidget(QLabel):
    def __init__(self, color=QColor(255, 255, 255, 255)):
        if isinstance(color, QColor):
           self.current_color = color
        else:
            # otherwise, it should be an rgb or rgba tuple
            if len(color) == 3:
                self.current_color = QColor(color[0], color[1], color[2], 255)
            else:
                self.current_color = QColor(color[0], color[1], color[2], color[3])
        super(QLabel, self).__init__("")
        self.setMinimumSize(30, 30)

        self.reset_style_sheet()

    def reset_style_sheet(self):
        color_string = "rgb(" + str(self.current_color.red()) + ", " + \
                        str(self.current_color.green()) + ", " + \
                        str(self.current_color.blue()) + ")"
        self.setStyleSheet("QLabel { background-color : "+ color_string + "; "
                           "border-style: outset;"
                           "border-width: 2px;"
                           "border-color: beige;}")

    def set_color(self, color):
        self.current_color = color

    def mousePressEvent(self, e):
        color_dialog = QColorDialog()
        color_dialog.exec_()
        self.current_color = color_dialog.selectedColor()
        self.reset_style_sheet()

    def value(self):
        return self.current_color