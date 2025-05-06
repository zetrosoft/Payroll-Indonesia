# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-06 18:55:10 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint

# Import utility functions
from payroll_indonesia.payroll_indonesia.utils import get_default_config, debug_log

class PPh21TERTable(Document):
    def validate(self):
        """Validate TER rate settings"""
        # Ensure fields are converted to proper types
        self.income_from = flt(self.income_from)
        self.income_to = flt(self.income_to)
        self.rate = flt(self.rate)
        self.is_highest_bracket = cint(self.is_highest_bracket)
        
        # Validate required fields
        if not self.status_pajak:
            frappe.throw(_("Tax Status (status_pajak) is required"))
            
        # Validate rate is within acceptable range
        if self.rate < 0 or self.rate > 100:
            frappe.throw(_("Tax rate must be between 0 and 100 percent"))
        
        # Validate income range
        self.validate_range()
        
        # Check for duplicates
        self.validate_duplicate()
        
        # Cross-check with configuration
        self.validate_against_config()
        
        # Set highest bracket flag if appropriate
        if self.income_to == 0 and not self.is_highest_bracket:
            self.is_highest_bracket = 1
            debug_log(f"Setting highest bracket flag for {self.status_pajak} with income_from {self.income_from}", 
                     "PPh 21 TER Table")
        
        # Generate description
        self.generate_description()
    
    def validate_range(self):
        """Validate income range"""
        if self.income_from < 0:
            frappe.throw(_("Income From cannot be negative"))
        
        if self.income_to > 0 and self.income_from >= self.income_to:
            frappe.throw(_("Income From must be less than Income To"))
        
        # For highest bracket, income_to should be 0
        if self.income_to == 0 and not self.is_highest_bracket:
            self.is_highest_bracket = 1
        elif self.is_highest_bracket and self.income_to > 0:
            self.income_to = 0
            debug_log(f"Set income_to to 0 for highest bracket for {self.status_pajak}", "PPh 21 TER Table")
    
    def validate_duplicate(self):
        """Check for duplicate status+range combinations"""
        if not self.is_new():
            # Only check for duplicates when creating new records
            return
        
        exists = frappe.db.exists(
            "PPh 21 TER Table",
            {
                "name": ["!=", self.name],
                "status_pajak": self.status_pajak,
                "income_from": self.income_from,
                "income_to": self.income_to
            }
        )
        
        if exists:
            frappe.throw(_(
                "Duplicate TER rate exists for status {0} with range {1} to {2}"
            ).format(
                self.status_pajak,
                format_currency(self.income_from),
                format_currency(self.income_to) if self.income_to > 0 else "∞"
            ))
    
    def validate_against_config(self):
        """Validate against TER rates in configuration"""
        try:
            # Get TER rates from configuration
            ter_rates = get_default_config("ter_rates")
            if not ter_rates:
                debug_log("No TER rates found in configuration", "PPh 21 TER Table")
                return
            
            # Check if status_pajak exists in configuration
            if self.status_pajak not in ter_rates:
                debug_log(f"Status {self.status_pajak} not found in TER configuration", "PPh 21 TER Table")
                return
            
            # Check if this range exists in configuration
            status_rates = ter_rates[self.status_pajak]
            for rate_data in status_rates:
                income_from = flt(rate_data.get("income_from", 0))
                income_to = flt(rate_data.get("income_to", 0))
                rate = flt(rate_data.get("rate", 0))
                
                # If we find a matching range, validate the rate matches configuration
                if self.income_from == income_from and self.income_to == income_to:
                    if self.rate != rate:
                        debug_log(
                            f"TER rate {self.rate}% for {self.status_pajak} range {self.income_from}-{self.income_to} "
                            f"does not match configuration value of {rate}%",
                            "PPh 21 TER Table"
                        )
                    break
            
        except Exception as e:
            frappe.log_error(
                f"Error validating TER rate against configuration: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "PPh 21 TER Validation Error"
            )
            debug_log(f"Error validating TER rate against config: {str(e)}", "PPh 21 TER Table", trace=True)
    
    def generate_description(self):
        """Set the description automatically with proper formatting"""
        # Generate the income range part of the description
        if self.income_from == 0:
            # Starting from 0
            if self.income_to > 0:
                income_range = f"≤ Rp{format_currency(self.income_to)}"
            else:
                # This shouldn't happen (income_from=0, income_to=0)
                income_range = f"Rp{format_currency(self.income_from)}"
        elif self.income_to == 0 or self.is_highest_bracket:
            # Highest bracket
            income_range = f"> Rp{format_currency(self.income_from)}"
        else:
            # Regular range
            income_range = f"Rp{format_currency(self.income_from)}-Rp{format_currency(self.income_to)}"
        
        # Set the description
        self.description = f"{self.status_pajak} {income_range}"
    
    def before_save(self):
        """
        Final validations and setups before saving
        """
        # Ensure is_highest_bracket is set correctly
        if self.income_to == 0:
            self.is_highest_bracket = 1
        
        # Ensure description is generated
        if not self.description:
            self.generate_description()

def format_currency(amount):
    """Format amount as currency with proper thousand separators"""
    try:
        # Format with thousand separator
        formatted = f"{flt(amount):,.0f}"
        # Replace commas with dots for Indonesian formatting
        return formatted.replace(",", ".")
    except Exception:
        return str(amount)