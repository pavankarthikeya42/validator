import pandas as pd
from typing import Dict, Optional

class ExcelValidator:
    def __init__(self, excel_path: str = r"C:\Users\karthikeya\Downloads\medicines-output-medicines-report_en.xlsx"):
        self.excel_path = excel_path
        self.df = None
        
    def load(self):
        if self.df is None:
            self.df = pd.read_excel(self.excel_path)
            # Ensure columns are string for easier comparison
            self.df.columns = [str(c).strip() for c in self.df.columns]
            
    def validate_metadata(self, ui_data: Dict[str, str]) -> Dict[str, dict]:
        """
        Validates General Information fields from ui_data against the Excel file.
        Uses the Generic Name / Review Name to find the corresponding row.
        """
        self.load()
        results = {}
        
        # 1. Identify the search key
        search_value = ui_data.get("Generic Name") or ui_data.get("Review Name") or ui_data.get("Product Name")
        if not search_value:
            # Fall back to trying to match by some standard
            search_value = ui_data.get("Application #")
            
        if not search_value:
            return {"error": "No generic name, review name, or application # found in UI to search Excel."}
            
        search_value = str(search_value).strip().lower()
        
        # Find row by International non-proprietary name (INN) or Medicine name
        matched_row = None
        for idx, row in self.df.iterrows():
            inn = str(row.get("International non-proprietary name (INN) / common name", "")).lower()
            med_name = str(row.get("Medicine name", "")).lower()
            
            if search_value in inn or search_value in med_name or inn in search_value or med_name in search_value:
                matched_row = row
                break
                
        if matched_row is None:
            # Check by authorization number if available
            app_num = str(ui_data.get("Application #", "")).lower()
            if app_num:
                for idx, row in self.df.iterrows():
                    auth_num = str(row.get("Marketing authorisation number", "")).lower()
                    if app_num in auth_num or auth_num in app_num:
                        matched_row = row
                        break
                        
        if matched_row is None:
            return {"error": f"Could not find any row in Excel matching {search_value}"}
            
        # Field Mappings: UI Field -> Excel Column
        field_mappings = {
            "Generic Name": "International non-proprietary name (INN) / common name",
            "Review Name": "Medicine name",
            "Product Name": "Medicine name",
            "Therapeutic Areas": "Therapeutic area (MeSH)",
            "Pharmacologic Class": "Pharmacotherapeutic group",
            "Dosage Form": "Pharmaceutical form",
            "Marketing Authorisation Holder": "Marketing authorisation holder/company name",
            "Date Of First Authorisation": "Date of issue of marketing authorisation valid throughout the European Union",
            "Date Of Revision": "Revision date",
            "Initial Approval": "Date of issue of marketing authorisation valid throughout the European Union",
            "Revised Date": "Revision date",
            "Outcome": "Authorisation status",
            "Approval Type": "Conditional approval",
            "Variations": "Condition / obligation"
        }
        # Create a case-insensitive lookup dict for ui_data
        ui_data_lower = {k.lower(): v for k, v in ui_data.items()}
        
        for ui_field, excel_col in field_mappings.items():
            ui_val_raw = ui_data_lower.get(ui_field.lower(), "")
            ui_val = str(ui_val_raw).strip().lower()
            
            is_none_or_na = not ui_val or ui_val in ["none", "n/a"]
                
            if excel_col in self.df.columns:
                excel_val = str(matched_row.get(excel_col, "")).strip().lower()
                is_excel_empty = not excel_val or excel_val == "nan"
                
                # If both are empty, it's a PASS (or PARTIAL to indicate placeholder)
                if is_none_or_na and is_excel_empty:
                    results[ui_field] = {
                        "section": ui_field,
                        "status": "PARTIAL",
                        "similarity": 100.0,
                        "matched_text": [],
                        "missing_text": ["No data provided in UI or Excel"],
                        "pdf_pages": ["Excel"],
                        "skipped": False
                    }
                # If UI is empty but Excel has data, it's a FAIL
                elif is_none_or_na and not is_excel_empty:
                    results[ui_field] = {
                        "section": ui_field,
                        "status": "FAIL",
                        "similarity": 0.0,
                        "matched_text": [],
                        "missing_text": [f"Expected: {matched_row.get(excel_col, 'N/A')}"],
                        "pdf_pages": ["Excel"],
                        "skipped": False
                    }
                # Check for match
                elif ui_val in excel_val or excel_val in ui_val:
                    results[ui_field] = {
                        "section": ui_field,
                        "status": "PASS",
                        "similarity": 100.0,
                        "matched_text": [ui_data.get(ui_field)],
                        "missing_text": [],
                        "pdf_pages": ["Excel"],
                        "skipped": False
                    }
                else:
                    results[ui_field] = {
                        "section": ui_field,
                        "status": "FAIL",
                        "similarity": 0.0,
                        "matched_text": [],
                        "missing_text": [f"Expected: {matched_row.get(excel_col, 'N/A')}"],
                        "pdf_pages": ["Excel"],
                        "skipped": False
                    }
                    
        return results
