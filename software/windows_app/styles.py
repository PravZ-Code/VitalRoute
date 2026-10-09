"""Hospital Triage Windows Application Theme and QSS Styles."""

DARK_MEDICAL_THEME = """
QMainWindow {
    background-color: #0b0f19;
    color: #f1f5f9;
}

QWidget {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #f1f5f9;
}

/* Group Boxes / Cards */
QGroupBox {
    background-color: #141c2e;
    border: 1px solid #23314d;
    border-radius: 8px;
    margin-top: 18px;
    padding: 14px 10px 10px 10px;
    font-weight: bold;
    color: #93c5fd;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 6px;
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 4px;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    border: 1px solid #334155;
    color: #f8fafc;
    padding: 8px 14px;
    border-radius: 6px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2e3e57;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #1a2333;
}

QPushButton:disabled {
    background-color: #111827;
    border-color: #1f2937;
    color: #4b5563;
}

QPushButton#btnConfirm {
    background-color: #059669;
    border-color: #10b981;
    color: #ffffff;
    font-size: 14px;
    font-weight: bold;
    padding: 10px 16px;
}

QPushButton#btnConfirm:hover {
    background-color: #10b981;
}

QPushButton#btnConstraint {
    background-color: #991b1b;
    border-color: #ef4444;
    color: #ffffff;
    font-size: 13px;
    font-weight: bold;
    padding: 10px 16px;
}

QPushButton#btnConstraint:hover {
    background-color: #dc2626;
}

QPushButton#btnUpdateCapacity {
    background-color: #1d4ed8;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: bold;
}

QPushButton#btnUpdateCapacity:hover {
    background-color: #2563eb;
}

/* Inputs & Combos */
QLineEdit, QSpinBox, QComboBox, QTextEdit {
    background-color: #0b0f19;
    border: 1px solid #23314d;
    border-radius: 5px;
    padding: 6px 8px;
    color: #ffffff;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #141c2e;
    selection-background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #23314d;
}

/* Table Widget */
QTableWidget {
    background-color: #0f172a;
    alternate-background-color: #141f36;
    border: 1px solid #23314d;
    border-radius: 6px;
    gridline-color: #1e293b;
    selection-background-color: #1e3a8a;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #172033;
    color: #94a3b8;
    padding: 8px;
    border: 1px solid #23314d;
    font-weight: bold;
    font-size: 12px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #0b0f19;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

/* Status Bar */
QStatusBar {
    background-color: #080c14;
    border-top: 1px solid #1e293b;
    color: #94a3b8;
}
"""
