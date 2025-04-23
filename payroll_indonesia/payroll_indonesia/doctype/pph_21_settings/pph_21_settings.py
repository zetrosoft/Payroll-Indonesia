from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class PPh21Settings(Document):
    def validate(self):
        """Validate PPh 21 settings"""
        if hasattr(self, 'bracket_table') and self.bracket_table:
            self.validate_bracket_table()
        if hasattr(self, 'ptkp_table') and self.ptkp_table:
            self.validate_ptkp_table()
        
    def validate_bracket_table(self):
        """Ensure tax brackets are continuous and non-overlapping"""
        if not self.bracket_table:
            frappe.msgprint("At least one tax bracket should be defined")
            return
        
        # Sort by income_from
        sorted_brackets = sorted(self.bracket_table, key=lambda x: x.income_from)
        
        # Check for gaps or overlaps
        for i in range(len(sorted_brackets) - 1):
            current = sorted_brackets[i]
            next_bracket = sorted_brackets[i + 1]
            
            if current.income_to != next_bracket.income_from:
                frappe.msgprint(f"Warning: Tax brackets should be continuous. Gap found between {current.income_to} and {next_bracket.income_from}")
    
    def validate_ptkp_table(self):
        """Ensure all PTKP status types are defined"""
        required_status = ["TK0", "K0", "K1", "K2", "K3"]
        
        if not self.ptkp_table:
            frappe.msgprint("PTKP values should be defined")
            return
        
        defined_status = [p.status_pajak for p in self.ptkp_table]
        
        for status in required_status:
            if status not in defined_status:
                frappe.msgprint(f"Warning: Missing PTKP definition for status: {status}")
    
    def get_ptkp_amount(self, status_pajak):
        """Get PTKP amount for a given tax status
        
        Args:
            status_pajak (str): Tax status (TK0, K0, K1, etc.)
            
        Returns:
            float: PTKP amount for the tax status
        """
        # Default value if not found
        default_ptkp = 54000000  # TK0 value
        
        if not hasattr(self, 'ptkp_table') or not self.ptkp_table:
            return default_ptkp
            
        for row in self.ptkp_table:
            if row.status_pajak == status_pajak:
                return float(row.ptkp_amount)
        
        # If status not found, return default TK0 value
        return default_ptkp
        
    @staticmethod
    def create_default_settings():
        """Create default PPh21Settings if it doesn't exist"""
        try:
            if not frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
                doc = frappe.new_doc("PPh 21 Settings")
                doc.calculation_method = "Progressive"
                doc.use_ter = 0
                
                # Basic PTKP values
                ptkp_values = {
                    "TK0": 54000000,  # tidak kawin, 0 tanggungan
                    "K0": 58500000    # kawin, 0 tanggungan
                }
                
                for status, amount in ptkp_values.items():
                    doc.append("ptkp_table", {
                        "status_pajak": status,
                        "ptkp_amount": amount
                    })
                
                # Basic tax brackets
                brackets = [
                    {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                    {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15}
                ]
                
                for bracket in brackets:
                    doc.append("bracket_table", bracket)
                
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                return doc
        except Exception as e:
            frappe.log_error(f"Error creating default PPh 21 Settings: {str(e)}")
            frappe.msgprint(f"Error creating PPh 21 Settings: {str(e)}", indicator="red")
            
        # If can't create, try to get existing
        try:
            return frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
        except:
            return None