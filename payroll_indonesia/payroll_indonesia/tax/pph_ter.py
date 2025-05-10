# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-10 12:10:00 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, cint

# Import central utility functions
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config, 
    debug_log
)

def setup_ter_rates():
    """
    Setup TER rates from defaults.json into PPh 21 TER Table
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        debug_log("Starting TER rates setup from configuration", "PPh 21 TER")
        
        # Get TER rates from configuration
        ter_rates = get_default_config("ter_rates")
        if not ter_rates:
            debug_log("No TER rates found in configuration", "PPh 21 TER Error")
            return False
            
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        # Process TER rates for each tax status
        for status_pajak, rates in ter_rates.items():
            debug_log(f"Processing {len(rates)} TER rates for status {status_pajak}", "PPh 21 TER")
            
            # Process each income bracket
            for i, rate_data in enumerate(rates):
                try:
                    # Extract values from rate data
                    income_from = flt(rate_data.get("income_from", 0))
                    income_to = flt(rate_data.get("income_to", 0))
                    rate_value = flt(rate_data.get("rate", 0))
                    
                    # Determine if this is the highest bracket (last index or income_to is 0)
                    is_highest_bracket = (i == len(rates) - 1 or income_to == 0)
                    
                    # Generate description
                    if is_highest_bracket:
                        description = f"{status_pajak} > Rp{income_from:,.0f}"
                    else:
                        description = f"{status_pajak} Rp{income_from:,.0f}-Rp{income_to:,.0f}"
                    
                    # Check if rate already exists in database
                    existing = frappe.db.exists("PPh 21 TER Table", {
                        "status_pajak": status_pajak,
                        "income_from": income_from,
                        "income_to": income_to
                    })
                    
                    if existing:
                        # Update existing rate if needed
                        existing_doc = frappe.get_doc("PPh 21 TER Table", existing)
                        if (existing_doc.rate != rate_value or 
                            existing_doc.is_highest_bracket != is_highest_bracket or
                            existing_doc.description != description):
                            
                            # Update existing rate
                            existing_doc.rate = rate_value
                            existing_doc.is_highest_bracket = is_highest_bracket
                            existing_doc.description = description
                            existing_doc.flags.ignore_permissions = True
                            existing_doc.save()
                            debug_log(f"Updated TER rate for {description}", "PPh 21 TER")
                            added_count += 1
                        else:
                            # Skip if no changes needed
                            skipped_count += 1
                    else:
                        # Create new TER rate
                        ter_entry = frappe.new_doc("PPh 21 TER Table")
                        ter_entry.status_pajak = status_pajak
                        ter_entry.income_from = income_from
                        ter_entry.income_to = income_to
                        ter_entry.rate = rate_value
                        ter_entry.is_highest_bracket = is_highest_bracket
                        ter_entry.description = description
                        
                        # Link to parent document if appropriate
                        if frappe.db.exists("DocType", "PPh 21 Settings"):
                            doc_list = frappe.db.get_all("PPh 21 Settings")
                            if doc_list:
                                ter_entry.parent = "PPh 21 Settings" 
                                ter_entry.parentfield = "ter_rates"
                                ter_entry.parenttype = "PPh 21 Settings"
                        
                        # Insert with permission bypass
                        ter_entry.flags.ignore_permissions = True
                        ter_entry.insert(ignore_permissions=True)
                        debug_log(f"Created new TER rate for {description}", "PPh 21 TER")
                        added_count += 1
                
                except Exception as e:
                    error_count += 1
                    frappe.log_error(
                        f"Error processing TER rate for {status_pajak} {income_from}-{income_to}: {str(e)}\n\n"
                        f"Traceback: {frappe.get_traceback()}", 
                        "PPh 21 TER Error"
                    )
                    # Remove trace parameter - it doesn't exist
                    debug_log(
                        f"Error processing TER rate for {status_pajak} {income_from}-{income_to}: {str(e)}", 
                        "PPh 21 TER Error"
                    )
        
        # Commit changes
        frappe.db.commit()
        
        # Log summary
        debug_log(
            f"TER rates setup summary: Created/updated: {added_count}, Skipped: {skipped_count}, Errors: {error_count}",
            "PPh 21 TER"
        )
        
        return error_count == 0
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Error setting up TER rates: {str(e)}\n\nTraceback: {frappe.get_traceback()}",
            "PPh 21 TER Error"
        )
        # Remove trace parameter - it doesn't exist
        debug_log(f"Error setting up TER rates: {str(e)}", "PPh 21 TER Error")
        return False

def get_ter_rate(status_pajak, income):
    """
    Get TER rate based on tax status and income amount
    
    Args:
        status_pajak (str): Tax status (e.g., 'TER A', 'TER B', 'TER C' or PTKP status)
        income (float): Monthly income amount
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Validate inputs
        if not status_pajak:
            status_pajak = "TER C"  # Default to highest category if not specified
            
        if not income or income <= 0:
            return 0
            
        # Map PTKP status to TER category if needed
        if status_pajak.startswith("TK") or status_pajak.startswith("K") or status_pajak.startswith("HB"):
            status_pajak = map_ptkp_to_ter_category(status_pajak)
            
        # Get TER rate from database
        ter = frappe.db.sql("""
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s <= income_to OR income_to = 0)
            ORDER BY income_from DESC
            LIMIT 1
        """, (status_pajak, income, income), as_dict=1)

        if ter and len(ter) > 0:
            return float(ter[0].rate) / 100.0
        else:
            # Try to find using highest available bracket
            ter = frappe.db.sql("""
                SELECT rate
                FROM `tabPPh 21 TER Table`
                WHERE status_pajak = %s
                  AND is_highest_bracket = 1
                LIMIT 1
            """, (status_pajak,), as_dict=1)
            
            if ter and len(ter) > 0:
                return float(ter[0].rate) / 100.0
            else:
                # As a last resort, use default rate from settings or hardcoded value
                try:
                    # Fall back to defaults.json values
                    config = get_default_config()
                    if config and "ter_rates" in config and status_pajak in config["ter_rates"]:
                        # Get the highest rate from the category
                        highest_rate = 0
                        for rate_data in config["ter_rates"][status_pajak]:
                            if "is_highest_bracket" in rate_data and rate_data["is_highest_bracket"]:
                                highest_rate = flt(rate_data["rate"])
                                break
                        
                        if highest_rate > 0:
                            return highest_rate / 100.0
                    
                    # PMK 168/2023 highest rate is 34% for all categories
                    return 0.34
                        
                except Exception:
                    # Last resort - use PMK 168/2023 highest rate
                    return 0.34
        
    except Exception as e:
        frappe.log_error(
            f"Error getting TER rate for category {status_pajak} and income {income}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Rate Error"
        )
        # Return PMK 168/2023 highest rate on error (34%)
        return 0.34

def map_ptkp_to_ter_category(status_pajak):
    """
    Map PTKP status to TER category based on PMK 168/2023
    
    Args:
        status_pajak (str): PTKP status (e.g., 'TK0', 'K1', etc.)
    
    Returns:
        str: TER category ('TER A', 'TER B', or 'TER C')
    """
    try:
        # Get mapping from defaults.json config
        try:
            from payroll_indonesia.payroll_indonesia.utils import get_default_config
            config = get_default_config()
            if config and "ptkp_to_ter_mapping" in config:
                mapping = config["ptkp_to_ter_mapping"]
            else:
                mapping = None
        except ImportError:
            mapping = None
        
        if not mapping:
            # Use hardcoded mapping based on PMK 168/2023
            mapping = {
                # TER A: PTKP TK/0 (Rp 54 juta/tahun)
                "TK0": "TER A",
                
                # TER B: PTKP K/0, TK/1, TK/2, K/1 (Rp 58,5-63 juta/tahun)
                "TK1": "TER B",
                "TK2": "TER B",
                "K0": "TER B",
                "K1": "TER B",
                
                # TER C: All other PTKP statuses with higher values
                "TK3": "TER C",
                "K2": "TER C", 
                "K3": "TER C",
                "HB0": "TER C",
                "HB1": "TER C",
                "HB2": "TER C",
                "HB3": "TER C"
            }
            
        # Return mapped category or default to TER C if status not found
        if status_pajak in mapping:
            return mapping[status_pajak]
        else:
            # Default to TER C for any unknown status
            return "TER C"
            
    except Exception as e:
        frappe.log_error(
            f"Error mapping PTKP status to TER category: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "TER Mapping Error"
        )
        # Default to TER C as safest option
        return "TER C"

def hitung_biaya_jabatan(penghasilan_bruto, is_annual=False):
    """
    Calculate Job Expense (Biaya Jabatan) based on tax configuration
    
    Args:
        penghasilan_bruto (float): Gross income
        is_annual (bool): Whether calculation is for annual income
        
    Returns:
        float: Job expense amount
    """
    # Get biaya jabatan settings from config
    config = get_default_config()
    tax_config = config.get("tax", {})
    
    # Get biaya jabatan percent and max from config or use defaults
    biaya_jabatan_percent = flt(tax_config.get("biaya_jabatan_percent", 5.0))
    biaya_jabatan_max = flt(tax_config.get("biaya_jabatan_max", 500000.0))
    
    # Calculate biaya jabatan
    biaya_jabatan = flt(penghasilan_bruto) * (biaya_jabatan_percent / 100.0)
    
    # Apply max amount limit
    max_amount = biaya_jabatan_max * 12 if is_annual else biaya_jabatan_max
    return min(biaya_jabatan, max_amount)

def hitung_pph_ter(penghasilan_bruto, status_pajak):
    """
    Calculate PPh 21 using TER method based on gross income and tax status
    
    Args:
        penghasilan_bruto (float): Gross income
        status_pajak (str): Tax status (TK0-TK3, K0-K3, HB0-HB3)
        
    Returns:
        dict: PPh 21 calculation result
    """
    if not penghasilan_bruto or penghasilan_bruto <= 0:
        return {
            "tax_amount": 0,
            "ter_rate": 0,
            "status": "No Income"
        }
    
    try:
        # Get TER rate using the local function
        ter_rate = get_ter_rate(status_pajak, penghasilan_bruto)
        
        # Calculate tax
        tax_amount = flt(penghasilan_bruto) * ter_rate
        
        return {
            "tax_amount": tax_amount,
            "ter_rate": ter_rate * 100,  # Convert to percent for display
            "status": "Success",
            "calculation_date": now_datetime()
        }
    except Exception as e:
        frappe.log_error(
            f"Error calculating TER for status {status_pajak} with income {penghasilan_bruto}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "PPh 21 TER Calculation Error"
        )
        # Remove trace parameter
        debug_log(
            f"Error calculating TER for status {status_pajak} with income {penghasilan_bruto}: {str(e)}",
            "PPh 21 TER Calculation Error"
        )
        return {
            "tax_amount": 0,
            "ter_rate": 0,
            "status": "Error",
            "error_message": str(e)
        }

def generate_ter_calculation_note(penghasilan_bruto, status_pajak, ter_result):
    """
    Generate detailed calculation note for TER method
    
    Args:
        penghasilan_bruto (float): Gross income
        status_pajak (str): Tax status
        ter_result (dict): Result from hitung_pph_ter
    
    Returns:
        str: Formatted calculation note
    """
    note = [
        "=== Perhitungan PPh 21 dengan TER ===",
        f"Status Pajak: {status_pajak}",
        f"Penghasilan Bruto: Rp {penghasilan_bruto:,.0f}",
        f"Tarif Efektif Rata-rata: {ter_result['ter_rate']:.2f}%",
        f"PPh 21: Rp {ter_result['tax_amount']:,.0f}"
    ]
    
    # Add reference to calculation method
    note.append("")
    note.append(f"Perhitungan sesuai PMK 168/2023 tentang Tarif Efektif Rata-rata")
    
    return "\n".join(note)

def should_use_ter():
    """
    Check if TER method should be used based on system settings
    
    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # First check config settings
        tax_config = get_default_config("tax")
        if tax_config:
            calc_method = tax_config.get("tax_calculation_method")
            use_ter = tax_config.get("use_ter")
            if calc_method == "TER" and use_ter:
                return True
                
        # If not determined from config, check DocType
        if frappe.db.exists("DocType", "PPh 21 Settings"):
            # Check if there are settings records
            doc_list = frappe.db.get_all("PPh 21 Settings")
            if not doc_list:
                return False
                
            # Get settings
            pph_settings = frappe.get_single("PPh 21 Settings")
            
            # Check required fields
            if not hasattr(pph_settings, 'calculation_method') or not hasattr(pph_settings, 'use_ter'):
                return False
                
            return (pph_settings.calculation_method == "TER" and cint(pph_settings.use_ter) == 1)
                
        return False
    except Exception as e:
        frappe.log_error(
            f"Error checking TER method settings: {str(e)}\n\nTraceback: {frappe.get_traceback()}",
            "PPh 21 TER Error"
        )
        # Remove trace parameter
        debug_log(f"Error checking TER method settings: {str(e)}", "PPh 21 TER Error")
        return False

def check_ter_setup():
    """
    Check if TER table is properly set up and attempt setup if missing
    
    Returns:
        bool: True if setup is complete, False otherwise
    """
    try:
        # Check if PPh 21 TER Table exists
        if not frappe.db.exists('DocType', 'PPh 21 TER Table'):
            debug_log("PPh 21 TER Table DocType does not exist", "PPh 21 TER Error")
            return False
        
        # Check if there are any TER rates defined
        count = frappe.db.count('PPh 21 TER Table')
        if count == 0:
            debug_log("No TER rates found, attempting setup from configuration", "PPh 21 TER")
            
            # Attempt to set up TER rates
            return setup_ter_rates()
        
        return True
    except Exception as e:
        frappe.log_error(
            f"Error checking TER setup: {str(e)}\n\nTraceback: {frappe.get_traceback()}",
            "PPh 21 TER Error"
        )
        # Remove trace parameter
        debug_log(f"Error checking TER setup: {str(e)}", "PPh 21 TER Error")
        return False