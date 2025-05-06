# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 18:45:21 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, now_datetime

# Import from central utilities
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config,
    debug_log,
    get_ptkp_settings,
    get_pph21_brackets
)

class PPh21Settings(Document):
    def validate(self):
        """Validate PPh 21 Settings"""
        debug_log("Validating PPh 21 Settings", "PPh 21 Settings")
        
        # Ensure required tables exist
        self.validate_bracket_table()
        self.validate_ptkp_table()
        
        # Ensure TER table exists if TER method is selected
        if self.calculation_method == "TER" and not self.use_ter:
            # Auto-set use_ter if calculation method is TER but use_ter isn't checked
            debug_log("Setting use_ter=1 because calculation_method=TER", "PPh 21 Settings")
            self.use_ter = 1
            
        if self.use_ter:
            self.validate_ter_table()
    
    def on_update(self):
        """Update settings when document is updated"""
        debug_log("Updating PPh 21 Settings", "PPh 21 Settings")
        
        # Ensure configuration is up to date
        self.update_settings_from_config()
    
    def validate_bracket_table(self):
        """Ensure tax brackets are continuous and non-overlapping"""
        if not self.bracket_table or len(self.bracket_table) == 0:
            debug_log("No tax brackets found, loading from configuration", "PPh 21 Settings")
            self.load_brackets_from_config()
            return
        
        # Sort by income_from
        sorted_brackets = sorted(self.bracket_table, key=lambda x: flt(x.income_from))
        
        # Check for gaps or overlaps
        for i in range(len(sorted_brackets) - 1):
            current = sorted_brackets[i]
            next_bracket = sorted_brackets[i + 1]
            
            if flt(current.income_to) != flt(next_bracket.income_from):
                frappe.msgprint(
                    _("Warning: Tax brackets should be continuous. Gap found between {0} and {1}").format(
                        current.income_to, next_bracket.income_from
                    ),
                    indicator="yellow"
                )
                debug_log(
                    f"Tax bracket gap found: {current.income_to} to {next_bracket.income_from}", 
                    "PPh 21 Settings"
                )

    def validate_ptkp_table(self):
        """Validate PTKP entries against required values"""
        config = get_default_config()
        
        # Required PTKP statuses from config or defaults
        ptkp_config = config.get("ptkp", {})
        required_status = list(ptkp_config.keys()) if ptkp_config else ["TK0", "K0", "K1", "K2", "K3"]
        
        if not self.ptkp_table or len(self.ptkp_table) == 0:
            debug_log("No PTKP values found, loading from configuration", "PPh 21 Settings")
            self.load_ptkp_from_config()
            return
        
        # Check if all required statuses are defined
        defined_status = [p.status_pajak for p in self.ptkp_table]
        
        for status in required_status:
            if status not in defined_status:
                frappe.msgprint(
                    _("Warning: Missing PTKP definition for status: {0}").format(status),
                    indicator="yellow"
                )
                debug_log(f"Missing PTKP definition for status: {status}", "PPh 21 Settings")

    def validate_ter_table(self):
        """Validate TER table if TER method is selected"""
        # Get TER table count - check across all status types
        count = frappe.db.count("PPh 21 TER Table")
        if count == 0:
            debug_log("No TER rates found in database, checking for default values", "PPh 21 Settings")
            
            # Load TER rates from config
            ter_rates = get_default_config("ter_rates")
            if ter_rates:
                debug_log(f"Creating TER rates from config for {len(ter_rates)} tax statuses", "PPh 21 Settings")
                self.load_ter_rates_from_config(ter_rates)
            else:
                frappe.msgprint(
                    _("Tarif Efektif Rata-rata (TER) belum didefinisikan di PPh 21 TER Table. "
                    "Silakan isi tabel tersebut sebelum menggunakan metode ini."),
                    indicator="yellow"
                )
                debug_log("No TER rates in config or database, user needs to define them", "PPh 21 Settings")

    def load_brackets_from_config(self):
        """Load tax brackets from configuration"""
        tax_brackets = get_pph21_brackets()
        
        if not tax_brackets:
            debug_log("No tax brackets found in configuration, creating default brackets", "PPh 21 Settings")
            return
            
        debug_log(f"Loading {len(tax_brackets)} tax brackets from configuration", "PPh 21 Settings")
        
        # Clear existing brackets
        self.set("bracket_table", [])
        
        # Add brackets from config
        for bracket in tax_brackets:
            if all(key in bracket for key in ['income_from', 'income_to', 'tax_rate']):
                self.append("bracket_table", {
                    "income_from": flt(bracket.get("income_from", 0)),
                    "income_to": flt(bracket.get("income_to", 0)),
                    "tax_rate": flt(bracket.get("tax_rate", 0))
                })
        
        # Sort brackets
        self.bracket_table.sort(key=lambda x: flt(x.income_from))

    def load_ptkp_from_config(self):
        """Load PTKP values from configuration"""
        ptkp_values = get_ptkp_settings()
        
        if not ptkp_values:
            debug_log("No PTKP values found in configuration, using default values", "PPh 21 Settings")
            return
            
        debug_log(f"Loading {len(ptkp_values)} PTKP values from configuration", "PPh 21 Settings")
        
        # Clear existing PTKP values
        self.set("ptkp_table", [])
        
        # Add PTKP values from config
        for status, amount in ptkp_values.items():
            # Skip non-standard keys used for PTKP calculation
            if status in ['pribadi', 'kawin', 'anak']:
                continue
                
            # Create appropriate description based on status
            description = self.get_ptkp_description(status)
            
            self.append("ptkp_table", {
                "status_pajak": status,
                "description": description,
                "ptkp_amount": flt(amount)
            })

    def load_ter_rates_from_config(self, ter_rates):
        """
        Load TER rates from configuration
        
        Args:
            ter_rates (dict): Dictionary of TER rates by tax status
        """
        if not ter_rates:
            return
            
        # For each status and its rates, create TER table entries
        for status, rates in ter_rates.items():
            debug_log(f"Creating {len(rates)} TER rates for status {status}", "PPh 21 Settings")
            
            for rate_data in rates:
                # Create TER rate entry
                ter_entry = frappe.new_doc("PPh 21 TER Table")
                ter_entry.parent = "PPh 21 Settings"
                ter_entry.parentfield = "ter_rates"
                ter_entry.parenttype = "PPh 21 Settings"
                ter_entry.status_pajak = status
                ter_entry.income_from = flt(rate_data.get("income_from", 0))
                ter_entry.income_to = flt(rate_data.get("income_to", 0))
                ter_entry.rate = flt(rate_data.get("rate", 0))
                
                # Insert with permission bypass
                ter_entry.insert(ignore_permissions=True)
        
        # Commit changes
        frappe.db.commit()
        debug_log("TER rates created successfully", "PPh 21 Settings")

    def get_ptkp_description(self, status):
        """
        Get description for PTKP status
        
        Args:
            status (str): PTKP status code (e.g., TK0, K1)
            
        Returns:
            str: Description of the PTKP status
        """
        # Parse status code
        if status.startswith("TK"):
            prefix = "Tidak Kawin"
            dependents = status[2:]
        elif status.startswith("K"):
            prefix = "Kawin"
            dependents = status[1:]
        elif status.startswith("HB"):
            prefix = "Kawin, Penghasilan Istri-Suami Digabung"
            dependents = status[2:]
        else:
            return status
        
        # Parse dependents
        try:
            num_dependents = int(dependents)
            if num_dependents == 0:
                return f"{prefix}, Tanpa Tanggungan"
            else:
                return f"{prefix}, {num_dependents} Tanggungan"
        except ValueError:
            return status

    def update_settings_from_config(self):
        """Update settings from configuration"""
        config = get_default_config()
        tax_config = config.get("tax", {})
        
        # Update calculation method if not set
        if not self.calculation_method and tax_config.get("tax_calculation_method"):
            self.calculation_method = tax_config.get("tax_calculation_method")
            debug_log(f"Setting calculation_method to {self.calculation_method} from config", "PPh 21 Settings")
        
        # Update TER settings
        if tax_config.get("use_ter") is not None and self.use_ter != tax_config.get("use_ter"):
            self.use_ter = cint(tax_config.get("use_ter"))
            debug_log(f"Setting use_ter to {self.use_ter} from config", "PPh 21 Settings")
        
        # Update gross up settings
        if tax_config.get("use_gross_up") is not None and self.use_gross_up != tax_config.get("use_gross_up"):
            self.use_gross_up = cint(tax_config.get("use_gross_up"))
            debug_log(f"Setting use_gross_up to {self.use_gross_up} from config", "PPh 21 Settings")
            
        # Update NPWP mandatory settings
        if tax_config.get("npwp_mandatory") is not None and self.npwp_mandatory != tax_config.get("npwp_mandatory"):
            self.npwp_mandatory = cint(tax_config.get("npwp_mandatory"))
            debug_log(f"Setting npwp_mandatory to {self.npwp_mandatory} from config", "PPh 21 Settings")
            
        # Update biaya jabatan settings
        if tax_config.get("biaya_jabatan_percent") is not None:
            self.biaya_jabatan_percent = flt(tax_config.get("biaya_jabatan_percent"))
            debug_log(f"Setting biaya_jabatan_percent to {self.biaya_jabatan_percent} from config", "PPh 21 Settings")
            
        if tax_config.get("biaya_jabatan_max") is not None:
            self.biaya_jabatan_max = flt(tax_config.get("biaya_jabatan_max"))
            debug_log(f"Setting biaya_jabatan_max to {self.biaya_jabatan_max} from config", "PPh 21 Settings")
            
        # Save changes if needed
        if self.has_value_changed("calculation_method") or \
           self.has_value_changed("use_ter") or \
           self.has_value_changed("use_gross_up") or \
           self.has_value_changed("npwp_mandatory") or \
           self.has_value_changed("biaya_jabatan_percent") or \
           self.has_value_changed("biaya_jabatan_max"):
            debug_log("Saving settings changes from config", "PPh 21 Settings")
            self.save()

def on_update(doc, method):
    """Handler for on_update event"""
    debug_log("PPh 21 Settings on_update called", "PPh 21 Settings")
    
    # Validate tax brackets
    validate_brackets(doc)
    
    # Validate PTKP entries
    validate_ptkp_entries(doc)
    
    # Validate TER table if needed
    if doc.calculation_method == "TER":
        validate_ter_table()

def validate_brackets(doc):
    """Ensure tax brackets are continuous and non-overlapping"""
    if not doc.bracket_table:
        frappe.msgprint(_("At least one tax bracket should be defined"))
        return
    
    # Sort by income_from
    sorted_brackets = sorted(doc.bracket_table, key=lambda x: flt(x.income_from))
    
    # Check for gaps or overlaps
    for i in range(len(sorted_brackets) - 1):
        current = sorted_brackets[i]
        next_bracket = sorted_brackets[i + 1]
        
        if flt(current.income_to) != flt(next_bracket.income_from):
            debug_log(f"Tax bracket gap found: {current.income_to} to {next_bracket.income_from}", "PPh 21 Settings")
            frappe.msgprint(
                _("Warning: Tax brackets should be continuous. Gap found between {0} and {1}").format(
                    current.income_to, next_bracket.income_from
                )
            )

def validate_ptkp_entries(doc):
    """Validate PTKP entries against required values"""
    # Get required statuses from config
    ptkp_config = get_default_config("ptkp")
    required_status = list(ptkp_config.keys()) if ptkp_config else ["TK0", "K0", "K1", "K2", "K3"]
    
    if not doc.ptkp_table:
        frappe.msgprint(_("PTKP values should be defined"))
        return
    
    defined_status = [p.status_pajak for p in doc.ptkp_table]
    
    for status in required_status:
        if status not in defined_status:
            debug_log(f"Missing PTKP definition for status: {status}", "PPh 21 Settings")
            frappe.msgprint(_("Warning: Missing PTKP definition for status: {0}").format(status))

def validate_ter_table():
    """Validate TER table if TER method is selected"""
    count = frappe.db.count("PPh 21 TER Table")
    if count == 0:
        frappe.msgprint(
            _("Tarif Efektif Rata-rata (TER) belum didefinisikan di PPh 21 TER Table. "
            "Silakan isi tabel tersebut sebelum menggunakan metode ini."),
            indicator="yellow"
        )
        debug_log("No TER rates defined in database", "PPh 21 Settings")

def update_from_config(doc=None):
    """
    Update PPh 21 Settings from configuration
    
    Args:
        doc (object, optional): PPh 21 Settings document. If None, will be fetched.
    """
    # Get PPh 21 Settings document
    if not doc:
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            doc_list = frappe.db.get_all("PPh 21 Settings")
            if doc_list:
                doc = frappe.get_single("PPh 21 Settings")
            else:
                # Create new settings document if not exists
                doc = frappe.new_doc("PPh 21 Settings")
    
    if not doc:
        debug_log("PPh 21 Settings document not found and could not be created", "PPh 21 Settings")
        return
    
    # Update settings from config
    config = get_default_config()
    tax_config = config.get("tax", {})
    
    # Set calculation method
    if tax_config.get("tax_calculation_method"):
        doc.calculation_method = tax_config.get("tax_calculation_method")
    else:
        doc.calculation_method = "Progressive"  # Default
    
    # Set TER usage
    doc.use_ter = cint(tax_config.get("use_ter", 0))
    
    # Set gross up
    doc.use_gross_up = cint(tax_config.get("use_gross_up", 0))
    
    # Set NPWP mandatory
    doc.npwp_mandatory = cint(tax_config.get("npwp_mandatory", 0))
    
    # Set biaya jabatan settings
    doc.biaya_jabatan_percent = flt(tax_config.get("biaya_jabatan_percent", 5.0))
    doc.biaya_jabatan_max = flt(tax_config.get("biaya_jabatan_max", 500000.0))
    
    # Save settings
    doc.flags.ignore_validate = True
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    
    # Reload document to ensure it's updated
    doc.reload()
    
    # Load PTKP values if needed
    if not doc.ptkp_table or len(doc.ptkp_table) == 0:
        doc.load_ptkp_from_config()
        doc.save(ignore_permissions=True)
    
    # Load tax brackets if needed
    if not doc.bracket_table or len(doc.bracket_table) == 0:
        doc.load_brackets_from_config()
        doc.save(ignore_permissions=True)
    
    debug_log("PPh 21 Settings updated from configuration", "PPh 21 Settings")
    
    # Check if TER rates need to be loaded
    if doc.calculation_method == "TER" and frappe.db.count("PPh 21 TER Table") == 0:
        ter_rates = get_default_config("ter_rates")
        if ter_rates:
            doc.load_ter_rates_from_config(ter_rates)
            
    frappe.db.commit()
    return doc