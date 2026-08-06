import logging
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QProgressBar, QTextEdit, 
                               QFileDialog, QMessageBox, QGroupBox, QRadioButton)
from PySide6.QtCore import QThreadPool
from core.worker import BatchWorker

class LogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        
    def emit(self, record):
        msg = self.format(record)
        self.callback(msg)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OutlineMiner - PDF TOC Extractor")
        self.resize(800, 600)
        
        self.threadpool = QThreadPool()
        self.worker = None
        self.root_folder = ""
        
        self.setup_ui()
        self.setup_logging()
        
    def setup_ui(self):
        # Apply a minimalist, clean, native-feeling stylesheet
        self.setStyleSheet("""
            QMainWindow { background-color: #FFFFFF; }
            QGroupBox {
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #E6E6E6;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 15px;
                color: #333333;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
            }
            QPushButton { 
                background-color: #F3F3F3; 
                color: #333333; 
                border: 1px solid #CCCCCC;
                border-radius: 4px; 
                padding: 6px 16px; 
                font-family: "Segoe UI", sans-serif;
            }
            QPushButton:hover { background-color: #EAEAEA; border-color: #AAAAAA; }
            QPushButton:pressed { background-color: #DEDEDE; }
            QPushButton:disabled { background-color: #F9F9F9; color: #BBBBBB; border-color: #EEEEEE; }
            
            QPushButton#startBtn {
                background-color: #0078D4;
                color: white;
                border: none;
                font-weight: bold;
                padding: 8px 24px;
            }
            QPushButton#startBtn:hover { background-color: #106EBE; }
            QPushButton#startBtn:disabled { background-color: #A0CBE8; color: #FFFFFF; }
            
            QTextEdit { 
                background-color: #FAFAFA; 
                border: 1px solid #E6E6E6; 
                border-radius: 4px; 
                font-family: Consolas, monospace;
                font-size: 12px;
                color: #444444;
                padding: 8px;
            }
            QLabel { font-family: "Segoe UI", sans-serif; font-size: 13px; color: #333333; }
            QProgressBar {
                border: 1px solid #E6E6E6;
                border-radius: 4px;
                text-align: center;
                background-color: #FAFAFA;
                color: #333333;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #0078D4;
                border-radius: 3px;
            }
        """)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 1. Configuration Group
        grp_config = QGroupBox("Configuration")
        lyt_config = QHBoxLayout(grp_config)
        self.btn_select = QPushButton("Select Folder")
        self.btn_select.clicked.connect(self.select_folder)
        self.lbl_folder = QLabel("No folder selected.")
        self.lbl_folder.setStyleSheet("color: #888888; font-style: italic;")
        lyt_config.addWidget(self.btn_select)
        lyt_config.addWidget(self.lbl_folder, stretch=1)
        layout.addWidget(grp_config)
        
        # 2. Progress Group
        grp_progress = QGroupBox("Status & Progress")
        lyt_progress = QVBoxLayout(grp_progress)
        
        stats_layout = QHBoxLayout()
        self.lbl_total = QLabel("Total PDFs: 0")
        self.lbl_success = QLabel("Success: 0")
        self.lbl_failed = QLabel("Failed: 0")
        stats_layout.addWidget(self.lbl_total)
        stats_layout.addWidget(self.lbl_success)
        stats_layout.addWidget(self.lbl_failed)
        lyt_progress.addLayout(stats_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        lyt_progress.addWidget(self.progress_bar)
        layout.addWidget(grp_progress)
        
        # 3. Log Group
        grp_log = QGroupBox("Activity Log")
        lyt_log = QVBoxLayout(grp_log)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        lyt_log.addWidget(self.txt_log)
        layout.addWidget(grp_log)
        
        # Bottom controls
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_processing)
        self.btn_stop.setEnabled(False)
        
        self.btn_start = QPushButton("Start Processing")
        self.btn_start.setObjectName("startBtn")
        self.btn_start.clicked.connect(self.start_processing)
        self.btn_start.setEnabled(False)
        
        bottom_layout.addWidget(self.btn_stop)
        bottom_layout.addWidget(self.btn_start)
        layout.addLayout(bottom_layout)
        
    def setup_logging(self):
        logger = logging.getLogger("OutlineMiner")
        logger.setLevel(logging.INFO)
        handler = LogHandler(self.append_log)
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    def append_log(self, text: str):
        self.txt_log.append(text)
        
    def select_folder(self):
        import os
        folder = QFileDialog.getExistingDirectory(self, "Select Root Folder")
        if folder:
            self.root_folder = folder
            self.lbl_folder.setText(folder)
            self.lbl_folder.setStyleSheet("color: #2f3640; font-weight: bold;")
            self.txt_log.clear()
            self.append_log(f"Selected folder: {folder}")
            
            # Count PDFs immediately
            self.append_log("Scanning folder for PDFs...")
            pdf_count = sum(1 for root, _, files in os.walk(folder) for f in files if f.lower().endswith(".pdf"))
            
            self.lbl_total.setText(f"Total PDFs: {pdf_count}")
            self.lbl_success.setText("Success: 0")
            self.lbl_failed.setText("Failed: 0")
            self.progress_bar.setValue(0)
            
            if pdf_count > 0:
                self.append_log(f"Found {pdf_count} PDF files ready for processing.")
                self.btn_start.setEnabled(True)
            else:
                self.append_log("No PDF files found in this folder or its subfolders.")
                self.btn_start.setEnabled(False)
            
    def start_processing(self):
        if not self.root_folder:
            return
            
        self.btn_start.setEnabled(False)
        self.btn_select.setEnabled(False)
        self.btn_stop.setEnabled(True)
        
        self.progress_bar.setValue(0)
        self.lbl_total.setText("Total PDFs: 0")
        self.lbl_success.setText("Success: 0")
        self.lbl_failed.setText("Failed: 0")
        self.txt_log.clear()
        
        self.worker = BatchWorker(self.root_folder)
        self.worker.signals.log.connect(self.append_log)
        self.worker.signals.progress.connect(self.progress_bar.setValue)
        self.worker.signals.stats_updated.connect(self.update_stats)
        self.worker.signals.error.connect(self.handle_error)
        self.worker.signals.finished.connect(self.processing_finished)
        
        self.threadpool.start(self.worker)
        
    def stop_processing(self):
        if self.worker:
            self.append_log("Stopping processing... Please wait.")
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            
    def update_stats(self, total: int, success: int, failed: int):
        self.lbl_total.setText(f"Total PDFs: {total}")
        self.lbl_success.setText(f"Success: {success}")
        self.lbl_failed.setText(f"Failed: {failed}")
        
    def handle_error(self, err_msg: str):
        QMessageBox.critical(self, "Error", err_msg)
        self.processing_finished()
        
    def processing_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_select.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if self.lbl_total.text() == "Total PDFs: 0":
            pass # No PDFs found, do not print error
        elif self.progress_bar.value() != 100:
            self.append_log("Process aborted or finished with errors.")
