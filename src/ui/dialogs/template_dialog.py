"""Project templates dialog — choose a ready-to-use starter project."""
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QTextEdit, QSplitter, QFrame, QWidget
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor

from src.core.project import Project
from src.core.models.pcb_board import PCBBoard, GraphicLine
from src.core.models.component import Component, Pad
from src.core.models.net import Net
from src.core.models.layer import Layer


@dataclass
class _Template:
    name: str
    category: str
    description: str
    mcu: str
    board_w: float
    board_h: float
    components: list[dict]


_STANDARD_LAYERS = [
    Layer("F.Cu", 0, "signal"), Layer("B.Cu", 31, "signal"),
    Layer("F.Paste", 35, "user"), Layer("B.Paste", 36, "user"),
    Layer("F.SilkS", 37, "user"), Layer("B.SilkS", 38, "user"),
    Layer("F.Mask", 39, "user"), Layer("B.Mask", 40, "user"),
    Layer("Edge.Cuts", 44, "user"),
]


def _edge(board_w, board_h) -> list[GraphicLine]:
    return [
        GraphicLine(0, 0, board_w, 0, 0.05, "Edge.Cuts"),
        GraphicLine(board_w, 0, board_w, board_h, 0.05, "Edge.Cuts"),
        GraphicLine(board_w, board_h, 0, board_h, 0.05, "Edge.Cuts"),
        GraphicLine(0, board_h, 0, 0, 0.05, "Edge.Cuts"),
    ]


def _c(ref, val, fp, x, y, desc="") -> Component:
    return Component(
        reference=ref, value=val, footprint=fp,
        x=x, y=y, description=desc,
    )


_TEMPLATES: list[_Template] = [
    _Template(
        name="ESP32 DevKit",
        category="ESP32 / WiFi",
        description=(
            "Płytka deweloperska z ESP32-WROOM-32D.\n"
            "• WiFi 802.11 b/g/n + BT 4.2\n"
            "• 38 GPIO, 2× UART, 2× I2C, 3× SPI\n"
            "• USB-UART via CP2102\n"
            "• 5V via USB-C lub VIN pin\n"
            "• LDO AMS1117-3V3\n"
            "• Wymiary: 52 × 28 mm\n\n"
            "Idealny do: IoT, czujniki WiFi, MQTT, HTTP serwery."
        ),
        mcu="ESP32-WROOM-32D",
        board_w=52, board_h=28,
        components=[
            ("U1", "ESP32-WROOM-32D", "RF_Module:ESP32-WROOM-32", 26, 14),
            ("U2", "CP2102", "Package_SO:SOIC-28", 10, 6),
            ("U3", "AMS1117-3V3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 44, 6),
            ("J1", "USB_C_Receptacle", "Connector_USB:USB_C_Receptacle_GCT_USB4085", 6, 14),
            ("J2", "Conn_01x19", "Connector_PinHeader_2.54mm:PinHeader_1x19_P2.54mm_Vertical", 2, 14),
            ("J3", "Conn_01x19", "Connector_PinHeader_2.54mm:PinHeader_1x19_P2.54mm_Vertical", 50, 14),
            ("SW1", "RESET", "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal_Wuerth_450301014042", 26, 4),
            ("SW2", "BOOT", "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal_Wuerth_450301014042", 30, 4),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 40, 10),
            ("C2", "10uF", "Capacitor_SMD:C_0805_2012Metric", 42, 10),
            ("LED1", "PWR", "LED_SMD:LED_0402_1005Metric", 48, 4),
        ],
    ),
    _Template(
        name="ESP32-S3 AI Board",
        category="ESP32 / WiFi",
        description=(
            "Płytka z ESP32-S3 — idealna do AI/ML na krawędzi.\n"
            "• Xtensa LX7 dual-core 240MHz\n"
            "• WiFi 802.11 b/g/n + BT 5 LE\n"
            "• USB OTG natywne (USB-C direct)\n"
            "• PSRAM 8MB opcjonalnie\n"
            "• 45 GPIO, LCD/Camera interface\n"
            "• Wymiary: 50 × 30 mm"
        ),
        mcu="ESP32-S3-WROOM-1",
        board_w=50, board_h=30,
        components=[
            ("U1", "ESP32-S3-WROOM-1", "RF_Module:ESP32-S3-WROOM-1", 25, 15),
            ("U2", "AMS1117-3V3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 43, 7),
            ("J1", "USB_C_Direct", "Connector_USB:USB_C_Receptacle_GCT_USB4085", 6, 15),
            ("J2", "Conn_01x20", "Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical", 2, 15),
            ("SW1", "RESET", "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal", 25, 4),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 40, 10),
            ("C2", "10uF", "Capacitor_SMD:C_0805_2012Metric", 42, 10),
            ("LED1", "PWR", "LED_SMD:LED_0402_1005Metric", 46, 4),
        ],
    ),
    _Template(
        name="Arduino Uno Shield",
        category="Arduino",
        description=(
            "Shield dla Arduino Uno/Mega (R3 footprint).\n"
            "• Złącza R3 kompatybilne (A0-A5, D0-D13)\n"
            "• I2C header: SDA/SCL\n"
            "• SPI header: MOSI/MISO/SCK/SS\n"
            "• 3.3V i 5V szyny zasilania\n"
            "• Obszar prototypowy 30×40mm\n"
            "• Wymiary: 68.6 × 53.4 mm"
        ),
        mcu="ATmega328P (Arduino Uno R3)",
        board_w=68.6, board_h=53.4,
        components=[
            ("J1", "Arduino_Uno_R3", "Shield:Arduino_UNO_R3", 34, 26),
            ("J2", "Conn_01x06_Power", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", 8, 6),
            ("J3", "Conn_01x08_Analog", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", 24, 6),
            ("J4", "Conn_01x08_Digital", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", 44, 6),
            ("J5", "Conn_01x06_Digital", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", 60, 6),
            ("J6", "Conn_01x04_I2C", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 8, 48),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 15, 15),
            ("C2", "100nF", "Capacitor_SMD:C_0402_1005Metric", 18, 15),
        ],
    ),
    _Template(
        name="STM32F103 Blue Pill",
        category="STM32",
        description=(
            "Klon 'Blue Pill' z STM32F103C8T6.\n"
            "• ARM Cortex-M3 72MHz, 64kB Flash, 20kB RAM\n"
            "• USB 2.0 Full Speed\n"
            "• 2× I2C, 3× USART, 2× SPI, 3× timer\n"
            "• 37 GPIO, 10× ADC (12-bit)\n"
            "• 8MHz HSE kryształ\n"
            "• Wymiary: 53 × 23 mm"
        ),
        mcu="STM32F103C8T6",
        board_w=53, board_h=23,
        components=[
            ("U1", "STM32F103C8T6", "Package_QFP:LQFP-48_7x7mm_P0.5mm", 26, 11),
            ("U2", "AMS1117-3V3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 48, 7),
            ("J1", "USB_Mini_B", "Connector_USB:USB_Mini-B_Lumberg_2486_01_Horizontal", 6, 11),
            ("J2", "Conn_01x20_Left", "Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical", 2, 11),
            ("J3", "Conn_01x20_Right", "Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical", 51, 11),
            ("Y1", "8MHz", "Crystal:Crystal_HC49-U_Vertical", 38, 5),
            ("SW1", "RESET", "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal", 26, 4),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 34, 10),
            ("C2", "22pF", "Capacitor_SMD:C_0402_1005Metric", 36, 5),
            ("C3", "22pF", "Capacitor_SMD:C_0402_1005Metric", 40, 5),
            ("LED1", "PC13", "LED_SMD:LED_0402_1005Metric", 46, 18),
            ("R1", "10k", "Resistor_SMD:R_0402_1005Metric", 20, 4),
        ],
    ),
    _Template(
        name="STM32F4 Discovery Clone",
        category="STM32",
        description=(
            "Płytka z STM32F407VGT6 — wydajna platforma embedded.\n"
            "• ARM Cortex-M4 168MHz + FPU\n"
            "• 1MB Flash, 192kB RAM\n"
            "• USB OTG FS/HS, Ethernet MAC, CAN\n"
            "• 2× I2C, 4× USART, 3× SPI, 14× timer\n"
            "• 10× ADC (12-bit), 2× DAC\n"
            "• Wymiary: 80 × 56 mm"
        ),
        mcu="STM32F407VGT6",
        board_w=80, board_h=56,
        components=[
            ("U1", "STM32F407VGT6", "Package_QFP:LQFP-100_14x14mm_P0.5mm", 40, 28),
            ("U2", "LD3985M33R", "Package_TO_SOT_SMD:SOT-23-5", 70, 10),
            ("J1", "USB_OTG_FS", "Connector_USB:USB_Micro-B_Molex-105017-0001", 10, 28),
            ("J2", "Conn_01x50_GPIO", "Connector_PinHeader_2.54mm:PinHeader_2x25_P2.54mm_Vertical", 5, 40),
            ("Y1", "8MHz_HSE", "Crystal:Crystal_HC49-U_Vertical", 60, 10),
            ("Y2", "32768_LSE", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", 65, 10),
            ("SW1", "RESET", "Button_Switch_SMD:SW_Push_1P1T_NO_Horizontal", 40, 5),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 30, 10),
            ("C2", "10uF", "Capacitor_SMD:C_0805_2012Metric", 33, 10),
            ("LED1", "LD3_RED", "LED_SMD:LED_0402_1005Metric", 70, 50),
            ("LED2", "LD4_BLUE", "LED_SMD:LED_0402_1005Metric", 73, 50),
        ],
    ),
    _Template(
        name="Raspberry Pi Pico (RP2040)",
        category="RP2040",
        description=(
            "Forma płytki inspirowana RPi Pico z RP2040.\n"
            "• Dual-core ARM Cortex-M0+ 133MHz\n"
            "• 264kB SRAM, 2MB Flash (QSPI)\n"
            "• USB 1.1 device/host natywne\n"
            "• 26 GPIO, 3× ADC, 2× I2C, 2× SPI, 2× UART\n"
            "• 8 PIO state machines\n"
            "• Wymiary: 51 × 21 mm"
        ),
        mcu="RP2040",
        board_w=51, board_h=21,
        components=[
            ("U1", "RP2040", "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", 25, 10),
            ("U2", "W25Q16JV", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 40, 10),
            ("U3", "RT6150B-33GQW", "Package_TO_SOT_SMD:SOT-23-5", 48, 6),
            ("J1", "USB_Micro_B", "Connector_USB:USB_Micro-B_Molex-105017-0001", 6, 10),
            ("J2", "Conn_01x20_Left", "Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical", 2, 10),
            ("J3", "Conn_01x20_Right", "Connector_PinHeader_2.54mm:PinHeader_1x20_P2.54mm_Vertical", 49, 10),
            ("Y1", "12MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", 16, 5),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 12, 10),
            ("C2", "10uF", "Capacitor_SMD:C_0805_2012Metric", 14, 10),
            ("LED1", "PWR", "LED_SMD:LED_0402_1005Metric", 46, 18),
        ],
    ),
    _Template(
        name="Zasilacz 12V→3V3/5V",
        category="Zasilanie",
        description=(
            "Moduł zasilania: buck converter 12V → 5V + LDO 5V → 3.3V.\n"
            "• MP2307 buck 12V→5V, 3A max\n"
            "• AMS1117-3V3 LDO 5V→3.3V, 1A\n"
            "• Wejście: DC Jack 5.5/2.1mm lub śrubowe\n"
            "• LED wskaźnik zasilania\n"
            "• Kondensatory filtrujące wejście/wyjście\n"
            "• Wymiary: 40 × 30 mm"
        ),
        mcu="Brak MCU — moduł zasilania",
        board_w=40, board_h=30,
        components=[
            ("U1", "MP2307", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 12, 10),
            ("U2", "AMS1117-3V3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 32, 10),
            ("J1", "DC_Jack_5.5mm", "Connector_BarrelJack:BarrelJack_Horizontal", 6, 15),
            ("J2", "Conn_01x03_5V_3V3_GND", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 37, 15),
            ("L1", "22uH", "Inductor_SMD:L_0805_2012Metric", 20, 10),
            ("D1", "SS34", "Diode_SMD:D_SMB", 20, 20),
            ("C1", "100uF_25V", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", 8, 25),
            ("C2", "47uF", "Capacitor_SMD:C_1206_3216Metric", 28, 10),
            ("C3", "100nF", "Capacitor_SMD:C_0402_1005Metric", 36, 6),
            ("C4", "10uF", "Capacitor_SMD:C_0805_2012Metric", 38, 6),
            ("R1", "100k", "Resistor_SMD:R_0402_1005Metric", 16, 6),
            ("R2", "47k", "Resistor_SMD:R_0402_1005Metric", 18, 6),
            ("LED1", "5V_OK", "LED_SMD:LED_0402_1005Metric", 36, 25),
            ("LED2", "3V3_OK", "LED_SMD:LED_0402_1005Metric", 39, 25),
        ],
    ),
    _Template(
        name="Sensor Node BLE (nRF52840)",
        category="Bluetooth / BLE",
        description=(
            "Węzeł sensorowy z nRF52840 (BLE 5).\n"
            "• ARM Cortex-M4F 64MHz + FPU\n"
            "• BLE 5.0, Thread, Zigbee, NFC\n"
            "• 1MB Flash, 256kB RAM\n"
            "• USB CDC natywne\n"
            "• BME280: temp/wilgotność/ciśnienie\n"
            "• Bateria CR2032 lub Li-Po\n"
            "• Wymiary: 45 × 35 mm"
        ),
        mcu="nRF52840",
        board_w=45, board_h=35,
        components=[
            ("U1", "nRF52840-QIAA", "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP3.5x3.5mm", 22, 17),
            ("U2", "BME280", "Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering", 38, 10),
            ("U3", "MCP73831", "Package_TO_SOT_SMD:SOT-23-5", 40, 28),
            ("J1", "USB_C", "Connector_USB:USB_C_Receptacle_GCT_USB4085", 6, 17),
            ("J2", "Conn_LiPo", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", 38, 30),
            ("BT1", "CR2032", "Battery:BatteryHolder_Keystone_3000_1x20mm", 10, 28),
            ("ANT1", "Chip_Antenna_2.4GHz", "RF_Antenna:Molex_2041500100_Chip", 8, 8),
            ("C1", "100nF", "Capacitor_SMD:C_0402_1005Metric", 30, 10),
            ("C2", "10uF", "Capacitor_SMD:C_0805_2012Metric", 32, 10),
            ("LED1", "BLE", "LED_SMD:LED_0402_1005Metric", 42, 20),
            ("LED2", "CHG", "LED_SMD:LED_0402_1005Metric", 42, 23),
        ],
    ),
]


def _build_board(tmpl: _Template) -> PCBBoard:
    components = []
    for i, (ref, val, fp, x, y, *rest) in enumerate(
            [(t[0], t[1], t[2], t[3], t[4]) for t in tmpl.components]):
        desc = ""
        components.append(Component(
            reference=ref, value=val, footprint=fp, x=x, y=y, description=desc
        ))

    board = PCBBoard(
        title=tmpl.name,
        components=components,
        graphic_lines=_edge(tmpl.board_w, tmpl.board_h),
        layers=_STANDARD_LAYERS[:],
    )
    return board


class TemplateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Szablony projektów")
        self.setMinimumSize(820, 560)
        self._selected_template: Optional[_Template] = None
        self._result_project: Optional[Project] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Wybierz szablon projektu")
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setStyleSheet("color: #4a90d9; margin-bottom: 6px;")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: list of templates ───────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        cat_label = QLabel("Kategoria / Szablon")
        cat_label.setStyleSheet("color: #888; font-size: 10px;")
        left_layout.addWidget(cat_label)

        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        self._list.currentRowChanged.connect(self._on_select)

        # Group by category
        current_cat = None
        for tmpl in _TEMPLATES:
            if tmpl.category != current_cat:
                current_cat = tmpl.category
                sep = QListWidgetItem(f"── {tmpl.category} ──")
                sep.setFlags(Qt.NoItemFlags)
                sep.setForeground(QColor("#4a90d9"))
                sep.setFont(QFont("Arial", 9, QFont.Bold))
                self._list.addItem(sep)
            item = QListWidgetItem(f"  {tmpl.name}")
            item.setData(Qt.UserRole, tmpl)
            self._list.addItem(item)

        left_layout.addWidget(self._list)
        splitter.addWidget(left)

        # ── Right: preview ────────────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel("Wybierz szablon…")
        self._title_label.setFont(QFont("Arial", 12, QFont.Bold))
        self._title_label.setStyleSheet("color: #e0e0e0;")
        right_layout.addWidget(self._title_label)

        self._mcu_label = QLabel("")
        self._mcu_label.setStyleSheet("color: #4a90d9; font-size: 11px; margin-bottom: 4px;")
        right_layout.addWidget(self._mcu_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #333;")
        right_layout.addWidget(line)

        self._desc = QTextEdit()
        self._desc.setReadOnly(True)
        self._desc.setFont(QFont("Consolas", 10))
        self._desc.setStyleSheet("background: #1a1a2e; border: none; color: #d0d0d0;")
        right_layout.addWidget(self._desc)

        self._comp_label = QLabel("")
        self._comp_label.setStyleSheet("color: #888; font-size: 10px;")
        right_layout.addWidget(self._comp_label)

        splitter.addWidget(right)
        splitter.setSizes([260, 540])
        layout.addWidget(splitter)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Anuluj")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self._btn_create = QPushButton("✅ Utwórz projekt")
        self._btn_create.setEnabled(False)
        self._btn_create.setStyleSheet(
            "QPushButton { background: #2a6faf; color: white; font-weight: bold; "
            "padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #3a8fdf; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self._btn_create.clicked.connect(self._on_create)
        btn_row.addWidget(self._btn_create)
        layout.addLayout(btn_row)

    def _on_select(self, row: int) -> None:
        item = self._list.item(row)
        if item is None:
            return
        tmpl: Optional[_Template] = item.data(Qt.UserRole)
        if tmpl is None:
            self._btn_create.setEnabled(False)
            return
        self._selected_template = tmpl
        self._title_label.setText(tmpl.name)
        self._mcu_label.setText(f"MCU: {tmpl.mcu}  |  {tmpl.board_w}×{tmpl.board_h} mm")
        self._desc.setPlainText(tmpl.description)
        self._comp_label.setText(f"Komponentów w szablonie: {len(tmpl.components)}")
        self._btn_create.setEnabled(True)

    def _on_create(self) -> None:
        if not self._selected_template:
            return
        board = _build_board(self._selected_template)
        self._result_project = Project(
            name=self._selected_template.name,
            board=board,
        )
        self.accept()

    def result_project(self) -> Optional[Project]:
        return self._result_project
