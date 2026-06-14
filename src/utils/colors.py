from PySide6.QtGui import QColor

LAYER_COLORS: dict[str, QColor] = {
    "F.Cu":      QColor(200,  50,  50, 200),
    "B.Cu":      QColor(  0, 100, 200, 200),
    "In1.Cu":    QColor(200, 150,   0, 180),
    "In2.Cu":    QColor(150, 200,   0, 180),
    "F.SilkS":   QColor(220, 220, 220, 220),
    "B.SilkS":   QColor(150, 220, 150, 220),
    "F.Mask":    QColor(200,   0, 150, 80),
    "B.Mask":    QColor(  0, 200, 150, 80),
    "F.Paste":   QColor(200, 200,   0, 80),
    "B.Paste":   QColor(  0, 200, 200, 80),
    "Edge.Cuts": QColor(255, 220,   0, 255),
    "F.CrtYd":   QColor(255, 255, 255, 100),
    "B.CrtYd":   QColor(180, 180, 255, 100),
    "F.Fab":     QColor(180, 180, 180, 120),
    "B.Fab":     QColor(100, 100, 180, 120),
}

VIA_COLOR   = QColor(220, 220,   0, 200)
PAD_COLOR   = QColor(230, 180,   0, 220)
BOARD_COLOR = QColor( 20,  60,  20, 255)


def layer_color(name: str) -> QColor:
    return LAYER_COLORS.get(name, QColor(180, 180, 180, 150))
