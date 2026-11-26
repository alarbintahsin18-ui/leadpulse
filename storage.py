import os
import csv
import json
import openpyxl
from datetime import datetime

COLUMNS = [
    "search_query",
    "search_type",
    "company_name",
    "domain",
    "first_name",
    "last_name",
    "contact_name",
    "contact_title",
    "email",
    "all_emails",
    "phone",
    "all_phones",
    "linkedin_url",
    "facebook_url",
    "twitter_url",
    "instagram_url",
    "date_extracted"
]

class HunterStorageManager:
    def __init__(self, data_dir=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = data_dir or base_dir
        self.xlsx_path = os.path.join(self.data_dir, "TS_Hunter_Extracted_Leads.xlsx")
        self.backup_xlsx_path = os.path.join(self.data_dir, "TS_Hunter_Extracted_Leads_backup.xlsx")
        self.csv_path = os.path.join(self.data_dir, "TS_Hunter_Extracted_Leads.csv")
        self.ensure_files()

    def safe_save(self, wb):
        try:
            wb.save(self.xlsx_path)
            self._sync_csv(wb)
            return True
        except PermissionError:
            print(f"[!] Warning: {self.xlsx_path} is open in Excel. Saving to backup.")
            try:
                wb.save(self.backup_xlsx_path)
                return True
            except Exception as e:
                print(f"[!] Backup save failed: {e}")
                return False
        except Exception as e:
            print(f"[!] Save failed: {e}")
            return False

    def ensure_files(self):
        if not os.path.exists(self.xlsx_path):
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Hunter_Leads"
            ws.append(COLUMNS)
            self.safe_save(wb)

    def save_lead(self, lead_data, query="", query_type=""):
        self.ensure_files()
        try:
            wb = openpyxl.load_workbook(self.xlsx_path)
        except Exception:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Hunter_Leads"
            ws.append(COLUMNS)

        ws = wb.active
        all_em_str = ", ".join(lead_data.get("all_emails", []))
        all_ph_str = ", ".join(lead_data.get("all_phones", []))

        row = [
            query,
            query_type,
            lead_data.get("company_name", ""),
            lead_data.get("domain", ""),
            lead_data.get("first_name", ""),
            lead_data.get("last_name", ""),
            lead_data.get("contact_name", ""),
            lead_data.get("contact_title", ""),
            lead_data.get("email", ""),
            all_em_str,
            lead_data.get("all_phones", [""])[0] if lead_data.get("all_phones") else "",
            all_ph_str,
            lead_data.get("linkedin_url", ""),
            lead_data.get("facebook_url", ""),
            lead_data.get("twitter_url", ""),
            lead_data.get("instagram_url", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]

        ws.append(row)
        self.safe_save(wb)

    def save_bulk_leads(self, results):
        """
        Saves a batch of results in a single open/save operation for performance.
        """
        self.ensure_files()
        try:
            wb = openpyxl.load_workbook(self.xlsx_path)
        except Exception:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Hunter_Leads"
            ws.append(COLUMNS)

        ws = wb.active
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for item in results:
            query = item.get("query", "")
            q_type = item.get("type", "")
            data = item.get("data", {})
            all_em_str = ", ".join(data.get("all_emails", []))
            all_ph_str = ", ".join(data.get("all_phones", []))

            row = [
                query,
                q_type,
                data.get("company_name", ""),
                data.get("domain", ""),
                data.get("first_name", ""),
                data.get("last_name", ""),
                data.get("contact_name", ""),
                data.get("contact_title", ""),
                data.get("email", ""),
                all_em_str,
                data.get("all_phones", [""])[0] if data.get("all_phones") else "",
                all_ph_str,
                data.get("linkedin_url", ""),
                data.get("facebook_url", ""),
                data.get("twitter_url", ""),
                data.get("instagram_url", ""),
                now_str
            ]
            ws.append(row)

        self.safe_save(wb)

    def clear_history(self):
        """
        Resets both Excel and CSV history files to headers only.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Hunter_Leads"
        ws.append(COLUMNS)
        self.safe_save(wb)
        return True

    def get_history(self):
        self.ensure_files()
        target = self.xlsx_path if os.path.exists(self.xlsx_path) else self.backup_xlsx_path
        if not os.path.exists(target):
            return []
        try:
            wb = openpyxl.load_workbook(target, data_only=True)
            ws = wb.active
            headers = [c.value for c in ws[1]]
            records = []
            for r in range(2, ws.max_row + 1):
                row_dict = {}
                for idx, h in enumerate(headers, start=1):
                    row_dict[h] = ws.cell(row=r, column=idx).value or ""
                if any(row_dict.values()):
                    records.append(row_dict)
            return list(reversed(records))
        except Exception as e:
            print(f"[!] History read warning: {e}")
            return []

    def _sync_csv(self, wb):
        try:
            ws = wb.active
            with open(self.csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                for r in ws.iter_rows(values_only=True):
                    writer.writerow([cell if cell is not None else "" for cell in r])
        except Exception:
            pass

