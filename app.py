import json
import sys
from pathlib import Path

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
    from PyQt6.QtWidgets import (
        QApplication,
        QComboBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSizePolicy,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise SystemExit(
        "PyQt6 is required for this QtWidgets GUI.\n"
        "Install it with: python3 -m pip install -r requirements.txt"
    ) from exc

from beam_solver import BeamLoad, BeamSolver


CROSS_SECTION_PATH = Path.home() / ".beam_calculator" / "cross_sections.json"


def calculate_polygon_properties(points):
    if len(points) < 3:
        raise ValueError("Use at least 3 points.")

    twice_area = 0.0
    centroid_x_factor = 0.0
    centroid_y_factor = 0.0
    ix_origin_factor = 0.0

    for i, (x0, y0) in enumerate(points):
        x1, y1 = points[(i + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        centroid_x_factor += (x0 + x1) * cross
        centroid_y_factor += (y0 + y1) * cross
        ix_origin_factor += (y0 * y0 + y0 * y1 + y1 * y1) * cross

    if abs(twice_area) < 1e-14:
        raise ValueError("The cross section has no enclosed area.")

    area_signed = twice_area / 2
    centroid_x = centroid_x_factor / (3 * twice_area)
    centroid_y = centroid_y_factor / (3 * twice_area)
    ix_origin_signed = ix_origin_factor / 12
    ix_centroid_signed = ix_origin_signed - area_signed * centroid_y * centroid_y

    area = abs(area_signed)
    ix_centroid = abs(ix_centroid_signed)
    c_value = max(abs(y - centroid_y) for _x, y in points)
    if ix_centroid <= 0 or c_value <= 0:
        raise ValueError("The cross section dimensions are too small to calculate useful section properties.")

    return {
        "area": area,
        "centroid_x": centroid_x,
        "centroid_y": centroid_y,
        "inertia_x": ix_centroid,
        "c": c_value,
    }


def load_cross_sections():
    try:
        with CROSS_SECTION_PATH.open("r", encoding="utf-8") as file:
            sections = json.load(file)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}

    valid = {}
    for name, section in sections.items():
        if isinstance(section, dict) and "points" in section and "properties" in section:
            valid[name] = section
    return valid


def save_cross_sections(sections):
    CROSS_SECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CROSS_SECTION_PATH.open("w", encoding="utf-8") as file:
        json.dump(sections, file, indent=2)


class PlotWidget(QWidget):
    def __init__(self, title, y_label, color):
        super().__init__()
        self.title = title
        self.y_label = y_label
        self.color = QColor(color)
        self.x_values = []
        self.y_values = []
        self.setMinimumHeight(165)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, x_values, y_values):
        self.x_values = x_values
        self.y_values = y_values
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfaf7"))

        rect = self.rect().adjusted(58, 28, -18, -32)
        painter.setPen(QColor("#292522"))
        painter.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(0, 6, 0, 0), Qt.AlignmentFlag.AlignHCenter, self.title)

        painter.setFont(QFont("Helvetica", 9))
        painter.save()
        painter.translate(18, self.height() / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-80, -12, 160, 24), Qt.AlignmentFlag.AlignCenter, self.y_label)
        painter.restore()

        if not self.x_values or not self.y_values:
            painter.setPen(QColor("#7d746b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Run calculation to plot results")
            return

        x_min, x_max = min(self.x_values), max(self.x_values)
        y_min, y_max = min(self.y_values), max(self.y_values)
        if abs(y_max - y_min) < 1e-12:
            y_min -= 1.0
            y_max += 1.0
        y_pad = 0.08 * (y_max - y_min)
        y_min -= y_pad
        y_max += y_pad

        def sx(value):
            return rect.left() + (value - x_min) / (x_max - x_min) * rect.width()

        def sy(value):
            return rect.top() + (y_max - value) / (y_max - y_min) * rect.height()

        zero_y = sy(0.0) if y_min <= 0 <= y_max else rect.bottom()
        painter.setPen(QPen(QColor("#aaa39a"), 1))
        painter.drawLine(QPointF(rect.left(), zero_y), QPointF(rect.right(), zero_y))
        painter.setPen(QPen(QColor("#6e665d"), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.topLeft(), rect.bottomLeft())

        path = QPainterPath()
        path.moveTo(sx(self.x_values[0]), sy(self.y_values[0]))
        for x, y in zip(self.x_values[1:], self.y_values[1:]):
            path.lineTo(sx(x), sy(y))

        fill_path = QPainterPath(path)
        fill_path.lineTo(sx(self.x_values[-1]), zero_y)
        fill_path.lineTo(sx(self.x_values[0]), zero_y)
        fill_path.closeSubpath()
        fill = QColor(self.color)
        fill.setAlpha(45)
        painter.fillPath(fill_path, fill)
        painter.setPen(QPen(self.color, 2))
        painter.drawPath(path)

        painter.setFont(QFont("Helvetica", 8))
        painter.setPen(QColor("#5d554d"))
        painter.drawText(QRectF(rect.left(), self.height() - 24, 120, 20), Qt.AlignmentFlag.AlignLeft, f"{x_min:g} m")
        painter.drawText(QRectF(rect.right() - 120, self.height() - 24, 120, 20), Qt.AlignmentFlag.AlignRight, f"{x_max:g} m")
        painter.drawText(QRectF(rect.left() + 4, rect.top() + 4, 160, 20), Qt.AlignmentFlag.AlignLeft, f"max {y_max:g}")
        painter.drawText(QRectF(rect.left() + 4, rect.bottom() - 20, 160, 20), Qt.AlignmentFlag.AlignLeft, f"min {y_min:g}")


class CrossSectionCanvas(QWidget):
    def __init__(self, on_change=None):
        super().__init__()
        self.on_change = on_change
        self.points = []
        self.properties = None
        self.view_size = 0.3
        self.setMinimumSize(560, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_view_size(self, value):
        self.view_size = value
        self.update()

    def set_points(self, points):
        self.points = points[:]
        self.update_properties()

    def update_properties(self):
        try:
            self.properties = calculate_polygon_properties(self.points)
        except ValueError:
            self.properties = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._screen_to_model(event.position())
        self.points.append(point)
        self.update_properties()
        if self.on_change:
            self.on_change()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfaf7"))

        plot = self.rect().adjusted(18, 18, -18, -18)
        side = min(plot.width(), plot.height())
        plot = QRectF(
            plot.center().x() - side / 2,
            plot.center().y() - side / 2,
            side,
            side,
        )

        painter.setPen(QPen(QColor("#e2dbcf"), 1))
        for i in range(11):
            offset = plot.left() + i * plot.width() / 10
            painter.drawLine(QPointF(offset, plot.top()), QPointF(offset, plot.bottom()))
            offset = plot.top() + i * plot.height() / 10
            painter.drawLine(QPointF(plot.left(), offset), QPointF(plot.right(), offset))

        origin = self._model_to_screen((0.0, 0.0), plot)
        painter.setPen(QPen(QColor("#b8afa3"), 1))
        painter.drawLine(QPointF(plot.left(), origin.y()), QPointF(plot.right(), origin.y()))
        painter.drawLine(QPointF(origin.x(), plot.top()), QPointF(origin.x(), plot.bottom()))

        if len(self.points) >= 2:
            path = QPainterPath()
            first = self._model_to_screen(self.points[0], plot)
            path.moveTo(first)
            for point in self.points[1:]:
                path.lineTo(self._model_to_screen(point, plot))
            if len(self.points) >= 3:
                path.closeSubpath()
                fill = QColor("#2f6f73")
                fill.setAlpha(45)
                painter.fillPath(path, fill)
            painter.setPen(QPen(QColor("#2f6f73"), 2))
            painter.drawPath(path)

        painter.setPen(QPen(QColor("#b25c3b"), 1, Qt.PenStyle.DashLine))
        if self.properties:
            neutral_y = self.properties["centroid_y"]
            y_screen = self._model_to_screen((0.0, neutral_y), plot).y()
            painter.drawLine(QPointF(plot.left(), y_screen), QPointF(plot.right(), y_screen))

        painter.setPen(QColor("#292522"))
        painter.setBrush(QColor("#fffdf9"))
        for index, point in enumerate(self.points, start=1):
            screen = self._model_to_screen(point, plot)
            painter.drawEllipse(screen, 4, 4)
            painter.drawText(QRectF(screen.x() + 6, screen.y() - 13, 32, 20), Qt.AlignmentFlag.AlignLeft, str(index))

        painter.setPen(QColor("#5d554d"))
        half = self.view_size / 2
        painter.drawText(QRectF(plot.left(), plot.bottom() + 2, 160, 18), Qt.AlignmentFlag.AlignLeft, f"{-half:g} m")
        painter.drawText(QRectF(plot.right() - 160, plot.bottom() + 2, 160, 18), Qt.AlignmentFlag.AlignRight, f"{half:g} m")

    def _screen_to_model(self, point):
        plot = self.rect().adjusted(18, 18, -18, -18)
        side = min(plot.width(), plot.height())
        plot = QRectF(
            plot.center().x() - side / 2,
            plot.center().y() - side / 2,
            side,
            side,
        )
        x = (point.x() - plot.center().x()) / plot.width() * self.view_size
        y = (plot.center().y() - point.y()) / plot.height() * self.view_size
        return (x, y)

    def _model_to_screen(self, point, plot):
        x, y = point
        return QPointF(
            plot.center().x() + x / self.view_size * plot.width(),
            plot.center().y() - y / self.view_size * plot.height(),
        )


class CrossSectionEditor(QWidget):
    def __init__(self, sections, on_saved):
        super().__init__()
        self.sections = sections
        self.on_saved = on_saved
        self._build_ui()
        self._update_result_text()

    def _build_ui(self):
        root = QGridLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setHorizontalSpacing(12)
        root.setColumnStretch(1, 1)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(360)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 14)
        panel_layout.setSpacing(10)

        setup = QGroupBox("Cross-section editor")
        form = QFormLayout(setup)
        self.name_input = self._line("Rectangular section")
        self.view_size_input = self._line("0.3")
        form.addRow("Name", self.name_input)
        form.addRow("Sketch window (m)", self.view_size_input)
        panel_layout.addWidget(setup)

        buttons = QGridLayout()
        undo = QPushButton("Undo point")
        clear = QPushButton("Clear")
        update_scale = QPushButton("Update scale")
        save = QPushButton("Save cross section")
        save.setObjectName("accent")
        undo.clicked.connect(self.undo_point)
        clear.clicked.connect(self.clear_points)
        update_scale.clicked.connect(self.update_scale)
        save.clicked.connect(self.save_section)
        buttons.addWidget(undo, 0, 0)
        buttons.addWidget(clear, 0, 1)
        buttons.addWidget(update_scale, 1, 0)
        buttons.addWidget(save, 1, 1)
        panel_layout.addLayout(buttons)

        library = QGroupBox("Saved sections")
        library_layout = QVBoxLayout(library)
        self.saved_list = QListWidget()
        self.saved_list.itemDoubleClicked.connect(lambda _item: self.load_selected_section())
        library_layout.addWidget(self.saved_list)
        load_selected = QPushButton("Load selected")
        load_selected.clicked.connect(self.load_selected_section)
        library_layout.addWidget(load_selected)
        panel_layout.addWidget(library)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        panel_layout.addWidget(self.result_text, 1)

        self.canvas = CrossSectionCanvas(self._update_result_text)
        self.canvas.setObjectName("canvas")

        root.addWidget(panel, 0, 0)
        root.addWidget(self.canvas, 0, 1)
        self._refresh_saved_list()

    def _line(self, default):
        line = QLineEdit(default)
        line.setMinimumHeight(30)
        return line

    def undo_point(self):
        if self.canvas.points:
            self.canvas.points.pop()
            self.canvas.update_properties()
            self._update_result_text()

    def clear_points(self):
        self.canvas.set_points([])
        self._update_result_text()

    def update_scale(self):
        try:
            value = float(self.view_size_input.text())
            if value <= 0:
                raise ValueError("Sketch window must be positive.")
            self.canvas.set_view_size(value)
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid scale", str(exc))

    def save_section(self):
        try:
            name = self.name_input.text().strip()
            if not name:
                raise ValueError("Enter a cross-section name.")
            properties = calculate_polygon_properties(self.canvas.points)
            self.sections[name] = {
                "points": [[x, y] for x, y in self.canvas.points],
                "properties": properties,
            }
            save_cross_sections(self.sections)
            self._refresh_saved_list()
            self.on_saved(name)
            self._update_result_text()
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Cannot save cross section", str(exc))

    def load_selected_section(self):
        item = self.saved_list.currentItem()
        if not item:
            return
        name = item.text()
        section = self.sections.get(name)
        if not section:
            return
        self.name_input.setText(name)
        self.canvas.set_points([(float(x), float(y)) for x, y in section["points"]])
        self._update_result_text()

    def _refresh_saved_list(self):
        self.saved_list.clear()
        for name in sorted(self.sections):
            self.saved_list.addItem(name)

    def _update_result_text(self):
        try:
            properties = calculate_polygon_properties(self.canvas.points)
        except ValueError:
            self.result_text.setPlainText("Area: -\nNeutral axis y_bar: -\nI_x: -\nc: -")
            return

        lines = [
            f"Area: {properties['area']:.6g} m^2",
            f"Neutral axis y_bar: {properties['centroid_y']:.6g} m",
            f"I_x about neutral axis: {properties['inertia_x']:.6g} m^4",
            f"c to extreme fiber: {properties['c']:.6g} m",
        ]
        self.result_text.setPlainText("\n".join(lines))


class BeamCalculatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.loads = []
        self.last_result = None
        self.cross_sections = load_cross_sections()
        self.setWindowTitle("Beam Calculator")
        self.resize(1240, 820)
        self.setMinimumSize(980, 720)
        self._build_ui()
        self._add_default_load()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        tabs = QTabWidget(central)
        root_shell = QVBoxLayout(central)
        root_shell.setContentsMargins(14, 14, 14, 14)
        root_shell.addWidget(tabs)

        beam_tab = QWidget()
        editor_tab = CrossSectionEditor(self.cross_sections, self._refresh_cross_section_combo)
        tabs.addTab(beam_tab, "Beam calculator")
        tabs.addTab(editor_tab, "Cross-section editor")

        root = QGridLayout(beam_tab)
        root.setContentsMargins(0, 0, 0, 0)
        root.setHorizontalSpacing(12)
        root.setColumnStretch(1, 1)

        inputs = QFrame()
        inputs.setObjectName("panel")
        inputs.setFixedWidth(360)
        input_layout = QVBoxLayout(inputs)
        input_layout.setContentsMargins(14, 14, 14, 14)
        input_layout.setSpacing(10)

        setup = QGroupBox("Beam setup")
        setup_layout = QFormLayout(setup)
        self.length_input = self._line("6.0")
        self.e_input = self._line("200e9")
        self.i_input = self._line("8.0e-6")
        self.c_input = self._line("0.075")
        self.nodes_input = self._line("41")
        self.cross_section_combo = QComboBox()
        self.cross_section_combo.currentTextChanged.connect(self._apply_selected_cross_section)
        setup_layout.addRow("Length L (m)", self.length_input)
        setup_layout.addRow("Elastic modulus E (Pa)", self.e_input)
        setup_layout.addRow("Cross section", self.cross_section_combo)
        setup_layout.addRow("Second moment I (m^4)", self.i_input)
        setup_layout.addRow("Extreme fiber c (m)", self.c_input)
        setup_layout.addRow("Solver nodes", self.nodes_input)

        self.left_support = QComboBox()
        self.right_support = QComboBox()
        for combo in (self.left_support, self.right_support):
            combo.addItems(["Fixed", "Pinned", "Roller", "Free"])
        self.left_support.setCurrentText("Pinned")
        self.right_support.setCurrentText("Roller")
        setup_layout.addRow("Left support", self.left_support)
        setup_layout.addRow("Right support", self.right_support)
        input_layout.addWidget(setup)

        loads = QGroupBox("Loads")
        load_layout = QVBoxLayout(loads)
        load_form = QFormLayout()
        self.load_kind = QComboBox()
        self.load_kind.addItems(["Point load", "Point moment", "UDL"])
        self.load_mag = self._line("-10000")
        self.load_pos = self._line("3.0")
        self.load_end = self._line("6.0")
        load_form.addRow("Type", self.load_kind)
        load_form.addRow("Magnitude", self.load_mag)
        load_form.addRow("Position/start (m)", self.load_pos)
        load_form.addRow("End for UDL (m)", self.load_end)
        load_layout.addLayout(load_form)

        load_buttons = QHBoxLayout()
        add_load = QPushButton("Add load")
        remove_load = QPushButton("Remove selected")
        add_load.clicked.connect(self.add_load)
        remove_load.clicked.connect(self.remove_load)
        load_buttons.addWidget(add_load)
        load_buttons.addWidget(remove_load)
        load_layout.addLayout(load_buttons)

        self.load_list = QListWidget()
        self.load_list.setMinimumHeight(120)
        load_layout.addWidget(self.load_list)
        input_layout.addWidget(loads)

        calculate = QPushButton("Calculate")
        calculate.setObjectName("accent")
        calculate.clicked.connect(self.calculate)
        input_layout.addWidget(calculate)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(150)
        input_layout.addWidget(self.summary, 1)

        plots = QWidget()
        plots_layout = QVBoxLayout(plots)
        plots_layout.setContentsMargins(0, 0, 0, 0)
        plots_layout.setSpacing(10)
        self.deflection_plot = PlotWidget("Deflection", "m", "#2f6f73")
        self.shear_plot = PlotWidget("Shear force", "N", "#b25c3b")
        self.moment_plot = PlotWidget("Bending moment", "N.m", "#5c659d")
        self.stress_plot = PlotWidget("Bending stress", "Pa", "#7b4e87")
        for plot in (self.deflection_plot, self.shear_plot, self.moment_plot, self.stress_plot):
            plots_layout.addWidget(plot)

        root.addWidget(inputs, 0, 0)
        root.addWidget(plots, 0, 1)
        self._refresh_cross_section_combo()
        self._apply_styles()

    def _line(self, default):
        line = QLineEdit(default)
        line.setMinimumHeight(30)
        return line

    def _apply_styles(self):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#ece8df"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#292522"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#fbfaf7"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f3efe7"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#292522"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#fffdf9"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#292522"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#7d746b"))
        self.setPalette(palette)
        self.setStyleSheet(
            """
            QWidget {
                color: #292522;
                selection-background-color: #2f6f73;
                selection-color: #ffffff;
            }
            QWidget#central { background: #ece8df; }
            QFrame#panel, QGroupBox, QTextEdit, QListWidget, QLineEdit, QComboBox {
                background: #fbfaf7;
                border: 1px solid #cfc8bd;
                border-radius: 6px;
                color: #292522;
            }
            QTabWidget::pane {
                border: 1px solid #cfc8bd;
                border-radius: 6px;
                background: #ece8df;
            }
            QTabBar::tab {
                background: #fffdf9;
                border: 1px solid #cfc8bd;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 14px;
                color: #292522;
            }
            QTabBar::tab:selected {
                background: #2f6f73;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: 700;
                margin-top: 10px;
                padding: 12px 10px 10px 10px;
                color: #292522;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #292522;
                background: #fbfaf7;
            }
            QLabel {
                color: #292522;
            }
            QLineEdit, QComboBox {
                padding: 5px 7px;
                color: #292522;
                background: #fffdf9;
            }
            QLineEdit:read-only {
                background: #f3efe7;
                color: #292522;
            }
            QComboBox QAbstractItemView {
                background: #fffdf9;
                color: #292522;
                border: 1px solid #cfc8bd;
                selection-background-color: #2f6f73;
                selection-color: #ffffff;
            }
            QPushButton {
                background: #fffdf9;
                border: 1px solid #aaa39a;
                border-radius: 6px;
                padding: 8px 10px;
                color: #292522;
            }
            QPushButton:hover { background: #f3efe7; }
            QPushButton#accent {
                background: #2f6f73;
                border-color: #2f6f73;
                color: white;
                font-weight: 700;
            }
            QTextEdit, QListWidget {
                padding: 6px;
                color: #292522;
                background: #fffdf9;
            }
            """
        )

    def _add_default_load(self):
        self.loads.append(BeamLoad("Point load", -10000.0, 3.0, 0.0))
        self._refresh_load_list()

    def _refresh_cross_section_combo(self, selected_name=None):
        if not hasattr(self, "cross_section_combo"):
            return
        current = selected_name or self.cross_section_combo.currentText() or "Manual I"
        self.cross_section_combo.blockSignals(True)
        self.cross_section_combo.clear()
        self.cross_section_combo.addItem("Manual I")
        for name in sorted(self.cross_sections):
            self.cross_section_combo.addItem(name)
        index = self.cross_section_combo.findText(current)
        self.cross_section_combo.setCurrentIndex(index if index >= 0 else 0)
        self.cross_section_combo.blockSignals(False)
        self._apply_selected_cross_section(self.cross_section_combo.currentText())

    def _apply_selected_cross_section(self, name):
        if name == "Manual I":
            self.i_input.setReadOnly(False)
            self.c_input.setReadOnly(False)
            return

        section = self.cross_sections.get(name)
        if not section:
            return
        properties = section["properties"]
        self.i_input.setText(f"{properties['inertia_x']:.8g}")
        self.c_input.setText(f"{properties['c']:.8g}")
        self.i_input.setReadOnly(True)
        self.c_input.setReadOnly(True)

    def add_load(self):
        try:
            kind = self.load_kind.currentText()
            magnitude = float(self.load_mag.text())
            position = float(self.load_pos.text())
            end_position = float(self.load_end.text())
            length = float(self.length_input.text())
            if position < 0 or position > length:
                raise ValueError("Load position must be inside the beam length.")
            if kind == "UDL" and (end_position <= position or end_position > length):
                raise ValueError("UDL end must be after the start and inside the beam length.")
            self.loads.append(BeamLoad(kind, magnitude, position, end_position))
            self._refresh_load_list()
        except ValueError as exc:
            QMessageBox.critical(self, "Invalid load", str(exc))

    def remove_load(self):
        row = self.load_list.currentRow()
        if row < 0:
            return
        del self.loads[row]
        self._refresh_load_list()

    def calculate(self):
        try:
            length = float(self.length_input.text())
            elastic_modulus = float(self.e_input.text())
            inertia = float(self.i_input.text())
            extreme_fiber = float(self.c_input.text())
            nodes = int(float(self.nodes_input.text()))

            if length <= 0 or elastic_modulus <= 0 or inertia <= 0 or extreme_fiber <= 0:
                raise ValueError("Length, E, I, and c must be positive.")
            if nodes < 3:
                raise ValueError("Use at least 3 solver nodes.")
            if not self.loads:
                raise ValueError("Add at least one load.")

            solver = BeamSolver(
                length,
                elastic_modulus,
                inertia,
                extreme_fiber,
                nodes,
                self.left_support.currentText(),
                self.right_support.currentText(),
                self.loads,
            )
            self.last_result = solver.solve()
            self._redraw_plots()
            self._write_summary()
        except ValueError as exc:
            QMessageBox.critical(self, "Calculation error", str(exc))

    def _redraw_plots(self):
        x = self.last_result["x"]
        self.deflection_plot.set_data(x, self.last_result["deflection"])
        self.shear_plot.set_data(x, self.last_result["shear"])
        self.moment_plot.set_data(x, self.last_result["moment"])
        self.stress_plot.set_data(x, self.last_result["stress"])

    def _write_summary(self):
        result = self.last_result
        d = result["deflection"]
        v = result["shear"]
        m = result["moment"]
        s = result["stress"]
        nodes = result["nodes"]
        reactions = result["reactions"]

        lines = [
            "Results",
            f"Max abs deflection: {max(d, key=abs):.6g} m",
            f"Max abs shear: {max(v, key=abs):.6g} N",
            f"Max abs moment: {max(m, key=abs):.6g} N.m",
            f"Max abs bending stress: {max(s, key=abs):.6g} Pa",
            "",
            "Support / nodal reactions",
        ]
        for node, x in enumerate(nodes):
            force = reactions[2 * node]
            moment = reactions[2 * node + 1]
            if abs(force) > 1e-6 or abs(moment) > 1e-6:
                lines.append(f"x={x:.4g} m: R={force:.6g} N, M={moment:.6g} N.m")

        lines.append("")
        lines.append("Sign convention: downward loads are negative; sagging moment follows the plotted sign.")
        self.summary.setPlainText("\n".join(lines))

    def _refresh_load_list(self):
        self.load_list.clear()
        for load in self.loads:
            self.load_list.addItem(load.label())


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = BeamCalculatorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
