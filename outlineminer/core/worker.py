import os
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, Signal
from .pipeline import process_pdf
from .writer import write_txt_output, write_csv_summary

class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    progress = Signal(int)
    log = Signal(str)
    stats_updated = Signal(int, int, int) # total, success, failed

class BatchWorker(QRunnable):
    def __init__(self, root_folder: str):
        super().__init__()
        self.root_folder = root_folder
        self.signals = WorkerSignals()
        self._is_running = True
        
    def stop(self):
        self._is_running = False

    def run(self):
        self.signals.log.emit(f"Scanning for PDFs in {self.root_folder}...")
        
        pdf_files = []
        try:
            for root, _, files in os.walk(self.root_folder):
                for file in files:
                    if file.lower().endswith(".pdf"):
                        pdf_files.append(os.path.join(root, file))
        except Exception as e:
            self.signals.error.emit(f"Failed to scan directory: {e}")
            return
            
        total_pdfs = len(pdf_files)
        if total_pdfs == 0:
            self.signals.log.emit("No PDFs found.")
            self.signals.finished.emit()
            return
            
        self.signals.log.emit(f"Found {total_pdfs} PDFs. Starting extraction...")
        
        success_count = 0
        fail_count = 0
        all_results = []
        
        for i, pdf_path in enumerate(pdf_files):
            if not self._is_running:
                self.signals.log.emit("Processing stopped by user.")
                break
                
            self.signals.log.emit(f"Processing: {os.path.basename(pdf_path)}")
            
            result = process_pdf(pdf_path, self.root_folder)
            all_results.append(result)
            
            write_txt_output(pdf_path, result)
            
            if result.status == "Success":
                success_count += 1
                self.signals.log.emit(f"SUCCESS ({result.source}): {result.pdf_name}")
            else:
                fail_count += 1
                self.signals.log.emit(f"FAILED: {result.pdf_name} - {result.error_message}")
                
            self.signals.progress.emit(int(((i + 1) / total_pdfs) * 100))
            self.signals.stats_updated.emit(total_pdfs, success_count, fail_count)
            
        self.signals.log.emit("Generating Summary Report...")
        write_csv_summary(self.root_folder, all_results)
        self.signals.log.emit("Finished processing.")
        self.signals.finished.emit()
