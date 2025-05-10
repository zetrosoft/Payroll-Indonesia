# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-08 11:46:04 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cstr, get_datetime_str, now_datetime

def override_salary_slip_gl_entries(doc, method=None):
    """
    Override GL entries for BPJS components in Salary Slip
    
    This function modifies GL entries for BPJS employer and employee components
    to use correct accounts from BPJS Account Mapping with standardized naming.
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function
    """
    try:
        doc_name = getattr(doc, 'name', 'Unknown')
        frappe.logger().debug(f"[{now_datetime().strftime('%Y-%m-%d %H:%M:%S')}] on_submit_salary_slip hook triggered for {doc_name}")
        
        # Skip if no earnings/deductions
        if not hasattr(doc, 'earnings') or not hasattr(doc, 'deductions') or (not doc.earnings and not doc.deductions):
            frappe.logger().debug(f"Skipping GL entry override for {doc_name}: No earnings or deductions found")
            return
        
        # Get company with fallback
        company = getattr(doc, 'company', None)
        if not company:
            frappe.logger().warning(f"Cannot override GL entries for Salary Slip {doc_name}: Missing company")
            return
        
        # Get BPJS account mapping for this company
        bpjs_mapping = get_bpjs_account_mapping(company)
        if not bpjs_mapping:
            frappe.logger().warning(f"BPJS Account Mapping not found for company {company}. Using default accounts.")
            return
        
        # Get existing GL entries that will be created
        try:
            gl_entries = get_existing_gl_entries(doc)
            if not gl_entries:
                frappe.logger().debug(f"No GL entries found for Salary Slip {doc_name}")
                return
        except Exception as e:
            frappe.logger().error(
                f"Error getting GL entries for Salary Slip {doc_name}: {str(e)}\n"
                f"Traceback: {frappe.get_traceback()}"
            )
            # Continue with standard GL entries
            return
        
        # Store company abbreviation for consistent use
        company_abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        # Modify GL entries for BPJS components
        modified_entries = []
        
        for entry in gl_entries:
            # Skip entries without 'against' field
            if not entry.get('against'):
                modified_entries.append(entry)
                continue
            
            # Check if this is a BPJS component
            component = entry.get('against', '')
            if "BPJS" not in component:
                modified_entries.append(entry)
                continue
            
            # Process the component based on standardized naming conventions
            try:
                modified_entry = process_bpjs_component_entry(entry, component, bpjs_mapping, company_abbr)
                modified_entries.append(modified_entry)
            except Exception as e:
                frappe.logger().error(
                    f"Error processing BPJS component {component} in {doc_name}: {str(e)}\n"
                    f"Traceback: {frappe.get_traceback()}"
                )
                # Keep original entry if processing fails
                modified_entries.append(entry)
        
        # Replace GL entries with our modified entries
        doc.gl_entries = modified_entries
        
    except Exception as e:
        frappe.logger().error(
            f"Critical error in override_salary_slip_gl_entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}"
        )
        # Don't re-raise - let the document submission continue with default GL entries

def override_payment_entry_gl_entries(doc, method=None):
    """
    Override GL entries for BPJS Payment Entry
    
    This function modifies GL entries for Payment Entries that reference BPJS Payment Summary
    to use correct accounts from defaults.json configuration with standardized naming.
    
    Args:
        doc (obj): Payment Entry document
        method (str, optional): Method that called this function
    """
    try:
        # Check if this is a BPJS payment
        is_bpjs_payment = False
        
        # Check references for BPJS Payment Summary
        if hasattr(doc, 'references') and doc.references:
            for ref in doc.references:
                if getattr(ref, 'reference_doctype', '') == 'BPJS Payment Summary':
                    is_bpjs_payment = True
                    break
        
        # Check party name for BPJS
        if not is_bpjs_payment and hasattr(doc, 'party') and 'BPJS' in doc.party:
            is_bpjs_payment = True
        
        # Check for BPJS in remarks
        if not is_bpjs_payment and hasattr(doc, 'remarks') and doc.remarks and 'BPJS' in doc.remarks:
            is_bpjs_payment = True
            
        if not is_bpjs_payment:
            return
            
        company = getattr(doc, 'company', None)
        if not company:
            return
            
        # Get gl_entries that would be created
        if not hasattr(doc, 'gl_entries') or not doc.gl_entries:
            return
            
        # Load BPJS account config from defaults.json
        mapping_config = frappe.get_file_json(frappe.get_app_path("payroll_indonesia", "config", "defaults.json"))
        bpjs_accounts = mapping_config.get("gl_accounts", {}).get("bpjs_payable_accounts", {})
        
        # Get company abbreviation
        company_abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        # Check if we need to modify each account
        for entry in doc.gl_entries:
            if "BPJS" not in entry.account:
                continue
                
            # Determine BPJS type from account name
            bpjs_type = None
            
            if "Kesehatan" in entry.account:
                bpjs_type = "kesehatan"
            elif "JHT" in entry.account:
                bpjs_type = "jht"
            elif "JP" in entry.account:
                bpjs_type = "jp"
            elif "JKK" in entry.account:
                bpjs_type = "jkk"
            elif "JKM" in entry.account:
                bpjs_type = "jkm"
                
            if bpjs_type and bpjs_accounts.get(f"{bpjs_type}_payable"):
                # Get account name from defaults.json
                account_name = bpjs_accounts[f"{bpjs_type}_payable"]["account_name"]
                standardized_account = f"{account_name} - {company_abbr}"
                
                # If account exists, update the entry
                if frappe.db.exists("Account", standardized_account):
                    entry.account = standardized_account
                    
        frappe.logger().debug(f"Modified GL entries for BPJS Payment Entry {doc.name}")
        
    except Exception as e:
        frappe.logger().error(
            f"Error in override_payment_entry_gl_entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}"
        )
        # Don't raise error, continue with original GL entries

def override_journal_entry_gl_entries(doc, method=None):
    """
    Override GL entries for Journal Entry linked to BPJS Payment Summary
    
    This function modifies GL entries for Journal Entries that reference BPJS Payment Summary
    to use correct accounts from defaults.json configuration with standardized naming.
    
    Args:
        doc (obj): Journal Entry document
        method (str, optional): Method that called this function
    """
    try:
        # Check if this is a BPJS journal entry
        is_bpjs_journal = False
        
        # Check references in accounts for BPJS Payment Summary
        if hasattr(doc, 'accounts') and doc.accounts:
            for acc in doc.accounts:
                if getattr(acc, 'reference_type', '') == 'BPJS Payment Summary':
                    is_bpjs_journal = True
                    break
        
        # Check for BPJS in user_remark
        if not is_bpjs_journal and hasattr(doc, 'user_remark') and doc.user_remark and 'BPJS' in doc.user_remark:
            is_bpjs_journal = True
            
        if not is_bpjs_journal:
            return
            
        company = getattr(doc, 'company', None)
        if not company:
            return
            
        # Get accounts that would be used
        if not hasattr(doc, 'accounts') or not doc.accounts:
            return
            
        # Load BPJS account config from defaults.json
        mapping_config = frappe.get_file_json(frappe.get_app_path("payroll_indonesia", "config", "defaults.json"))
        bpjs_expense_accounts = mapping_config.get("gl_accounts", {}).get("bpjs_expense_accounts", {})
        bpjs_payable_accounts = mapping_config.get("gl_accounts", {}).get("bpjs_payable_accounts", {})
        
        # Get company abbreviation
        company_abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        # Check if we need to modify each account
        for acc in doc.accounts:
            if "BPJS" not in acc.account:
                continue
                
            # Check if this is expense or payable
            is_expense = "Expense" in acc.account
            
            # Determine BPJS type from account name
            bpjs_type = None
            
            if "Kesehatan" in acc.account:
                bpjs_type = "kesehatan"
            elif "JHT" in acc.account:
                bpjs_type = "jht"
            elif "JP" in acc.account:
                bpjs_type = "jp"
            elif "JKK" in acc.account:
                bpjs_type = "jkk"
            elif "JKM" in acc.account:
                bpjs_type = "jkm"
                
            if bpjs_type:
                account_config = None
                
                if is_expense and bpjs_expense_accounts.get(f"bpjs_{bpjs_type}_employer_expense"):
                    # Get account name from defaults.json for expense
                    account_config = bpjs_expense_accounts[f"bpjs_{bpjs_type}_employer_expense"]
                elif not is_expense and bpjs_payable_accounts.get(f"bpjs_{bpjs_type}_payable"):
                    # Get account name from defaults.json for payable
                    account_config = bpjs_payable_accounts[f"bpjs_{bpjs_type}_payable"]
                    
                if account_config:
                    account_name = account_config["account_name"]
                    standardized_account = f"{account_name} - {company_abbr}"
                    
                    # If account exists, update the entry
                    if frappe.db.exists("Account", standardized_account):
                        acc.account = standardized_account
                    
        frappe.logger().debug(f"Modified accounts for BPJS Journal Entry {doc.name}")
        
    except Exception as e:
        frappe.logger().error(
            f"Error in override_journal_entry_gl_entries for {getattr(doc, 'name', 'Unknown')}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}"
        )
        # Don't raise error, continue with original accounts

def process_bpjs_component_entry(entry, component, bpjs_mapping, company_abbr=None):
    """
    Process a GL entry for a BPJS component to use correct accounts
    
    Args:
        entry (dict): Original GL entry
        component (str): BPJS component name
        bpjs_mapping (obj): BPJS Account Mapping document
        company_abbr (str, optional): Company abbreviation for fallback
        
    Returns:
        dict: Modified GL entry with updated account
    """
    # Make a copy to avoid modifying the original
    entry = dict(entry)
    
    # Handle different BPJS component types
    if "Employer" in component:
        # This is an employer contribution
        if "Kesehatan" in component:
            if entry.get('debit') and bpjs_mapping.kesehatan_employer_debit_account:
                entry['account'] = bpjs_mapping.kesehatan_employer_debit_account
            elif entry.get('credit') and bpjs_mapping.kesehatan_employer_credit_account:
                entry['account'] = bpjs_mapping.kesehatan_employer_credit_account
        elif "JHT" in component:
            if entry.get('debit') and bpjs_mapping.jht_employer_debit_account:
                entry['account'] = bpjs_mapping.jht_employer_debit_account
            elif entry.get('credit') and bpjs_mapping.jht_employer_credit_account:
                entry['account'] = bpjs_mapping.jht_employer_credit_account
        elif "JP" in component:
            if entry.get('debit') and bpjs_mapping.jp_employer_debit_account:
                entry['account'] = bpjs_mapping.jp_employer_debit_account
            elif entry.get('credit') and bpjs_mapping.jp_employer_credit_account:
                entry['account'] = bpjs_mapping.jp_employer_credit_account
        elif "JKK" in component:
            if entry.get('debit') and bpjs_mapping.jkk_employer_debit_account:
                entry['account'] = bpjs_mapping.jkk_employer_debit_account
            elif entry.get('credit') and bpjs_mapping.jkk_employer_credit_account:
                entry['account'] = bpjs_mapping.jkk_employer_credit_account
        elif "JKM" in component:
            if entry.get('debit') and bpjs_mapping.jkm_employer_debit_account:
                entry['account'] = bpjs_mapping.jkm_employer_debit_account
            elif entry.get('credit') and bpjs_mapping.jkm_employer_credit_account:
                entry['account'] = bpjs_mapping.jkm_employer_credit_account
    else:
        # This is an employee contribution (deduction)
        if "Kesehatan" in component and bpjs_mapping.kesehatan_employee_account:
            if entry.get('credit'):
                entry['account'] = bpjs_mapping.kesehatan_employee_account
        elif "JHT" in component and bpjs_mapping.jht_employee_account:
            if entry.get('credit'):
                entry['account'] = bpjs_mapping.jht_employee_account
        elif "JP" in component and bpjs_mapping.jp_employee_account:
            if entry.get('credit'):
                entry['account'] = bpjs_mapping.jp_employee_account
    
    # If not found in mapping but component is BPJS, use standardized account name as fallback
    if company_abbr and ("BPJS" in component) and (not entry.get('account') or entry.get('account') == ""):
        fallback_account = get_fallback_bpjs_account(component, company_abbr, entry.get('debit', 0) > 0)
        if fallback_account:
            entry['account'] = fallback_account
    
    return entry

def get_bpjs_account_mapping(company):
    """
    Get BPJS Account Mapping for this company
    
    Args:
        company (str): Company name
        
    Returns:
        obj: BPJS Account Mapping document or None if not found
    """
    try:
        # First try to use the cached mapping
        cache_key = f"bpjs_mapping_{company}"
        mapping_dict = frappe.cache().get_value(cache_key)
        
        if mapping_dict and isinstance(mapping_dict, dict) and mapping_dict.get("name"):
            # Convert back to document
            try:
                mapping = frappe.get_doc("BPJS Account Mapping", mapping_dict.get("name"))
                if mapping:
                    return mapping
            except:
                # Cache might be invalid, clear it
                frappe.cache().delete_value(cache_key)
        
        # If no cache or document not found, query directly
        mapping = frappe.get_all(
            "BPJS Account Mapping",
            filters={"company": company},
            limit=1
        )
        
        if mapping:
            return frappe.get_doc("BPJS Account Mapping", mapping[0].name)
        
        # Try to create mapping if it doesn't exist
        try:
            from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import create_default_mapping
            mapping_name = create_default_mapping(company)
            if mapping_name:
                return frappe.get_doc("BPJS Account Mapping", mapping_name)
        except ImportError:
            frappe.logger().warning(f"Could not import create_default_mapping for {company}")
    
    except Exception as e:
        frappe.logger().error(f"Error getting BPJS Account Mapping for {company}: {str(e)}")
    
    return None

def get_existing_gl_entries(slip_name):
    """Get existing GL entries for this Salary Slip to avoid duplicates"""
    try:
        gl_entries = frappe.db.get_all(
            "GL Entry",
            filters={
                "voucher_type": "Salary Slip",
                "voucher_no": slip_name,
                "is_cancelled": 0
            },
            fields=["name", "account", "against", "credit", "debit", "cost_center"]
        )
        
        # If no existing entries, return empty list
        if not gl_entries:
            return []
            
        # Process department to get cost center
        department = frappe.db.get_value('Salary Slip', slip_name, 'department')
        
        # Add cost center if not already in GL entries
        if department:
            try:
                # First check if cost_center column exists in Department table
                if frappe.db.has_column('Department', 'cost_center'):
                    cost_center = frappe.db.get_value('Department', department, 'cost_center')
                    if cost_center:
                        for entry in gl_entries:
                            if not entry.get('cost_center'):
                                entry['cost_center'] = cost_center
                else:
                    frappe.logger().debug(f"Department table does not have cost_center column")
                    
                    # Try to get cost center from Company
                    company = frappe.db.get_value('Salary Slip', slip_name, 'company')
                    if company:
                        cost_center = frappe.db.get_value('Company', company, 'cost_center')
                        if cost_center:
                            for entry in gl_entries:
                                if not entry.get('cost_center'):
                                    entry['cost_center'] = cost_center
            except Exception as e:
                frappe.log_error(
                    f"Error getting cost center for {slip_name}, department {department}: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "GL Entry Override Error"
                )
                # Continue processing without cost center
                pass
                
        return gl_entries
        
    except Exception as e:
        frappe.log_error(
            f"Error in get_existing_gl_entries for {slip_name}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "GL Entry Override Error"
        )
        return []

def get_component_account(salary_component, type_name, company):
    """
    Get the account for a salary component
    
    Args:
        salary_component (str): Name of salary component
        type_name (str): Type of component (earnings/deductions)
        company (str): Company name
        
    Returns:
        str: Account name or None if not found
    """
    try:
        # Try to get exact match first
        account = frappe.db.get_value(
            "Salary Component Account",
            {"parent": salary_component, "company": company},
            "account"
        )
        
        if not account:
            # Try with % wildcard
            account = frappe.db.get_value(
                "Salary Component Account",
                {"parent": salary_component, "company": "%"},
                "account"
            )
            
            if account:
                # Replace % with company name
                account = account.replace("%", company)
            else:
                # Try using BPJS default naming based on component
                account = get_default_bpjs_account(salary_component, type_name, company)
        
        return account
    except Exception as e:
        frappe.logger().error(f"Error getting account for component {salary_component}: {str(e)}")
        return None

def get_default_bpjs_account(component_name, type_name, company):
    """
    Get default BPJS account based on component name and type
    
    Args:
        component_name (str): Name of salary component
        type_name (str): Type of component (earnings/deductions)
        company (str): Company name
        
    Returns:
        str: Account name or None if not applicable
    """
    try:
        abbr = frappe.get_cached_value('Company', company, 'abbr')
        
        # Not a BPJS component
        if "BPJS" not in component_name:
            return None
        
        # Get standardized account name
        account_name = None
        
        if "Employer" in component_name:
            # Expense accounts for employer contributions
            if "Kesehatan" in component_name:
                account_name = f"BPJS Kesehatan Employer Expense - {abbr}"
            elif "JHT" in component_name:
                account_name = f"BPJS JHT Employer Expense - {abbr}"
            elif "JP" in component_name:
                account_name = f"BPJS JP Employer Expense - {abbr}"
            elif "JKK" in component_name:
                account_name = f"BPJS JKK Employer Expense - {abbr}"
            elif "JKM" in component_name:
                account_name = f"BPJS JKM Employer Expense - {abbr}"
        else:
            # Liability accounts for employee contributions
            if "Kesehatan" in component_name:
                account_name = f"BPJS Kesehatan Payable - {abbr}"
            elif "JHT" in component_name:
                account_name = f"BPJS JHT Payable - {abbr}"
            elif "JP" in component_name:
                account_name = f"BPJS JP Payable - {abbr}"
            elif "JKK" in component_name:
                account_name = f"BPJS JKK Payable - {abbr}"
            elif "JKM" in component_name:
                account_name = f"BPJS JKM Payable - {abbr}"
        
        # Check if account exists
        if account_name and frappe.db.exists("Account", account_name):
            return account_name
        
        # Try to find parent accounts as fallback
        if not account_name:
            if type_name == "earnings" or "Employer" in component_name:
                parent_account = f"BPJS Expenses - {abbr}"
                if frappe.db.exists("Account", parent_account):
                    return parent_account
            else:
                parent_account = f"BPJS Payable - {abbr}"
                if frappe.db.exists("Account", parent_account):
                    return parent_account
        
        return None
    except Exception as e:
        frappe.logger().error(f"Error getting default BPJS account: {str(e)}")
        return None

def get_fallback_bpjs_account(component_name, company_abbr, is_debit):
    """
    Get a fallback BPJS account when mapping doesn't provide one
    
    Args:
        component_name (str): BPJS component name
        company_abbr (str): Company abbreviation
        is_debit (bool): Whether this is a debit entry (for expense) or credit entry (for liability)
        
    Returns:
        str: Fallback account name or None
    """
    try:
        if is_debit:
            # For debit entries, use expense accounts
            if "Kesehatan" in component_name:
                return f"BPJS Kesehatan Employer Expense - {company_abbr}"
            elif "JHT" in component_name:
                return f"BPJS JHT Employer Expense - {company_abbr}"
            elif "JP" in component_name:
                return f"BPJS JP Employer Expense - {company_abbr}"
            elif "JKK" in component_name:
                return f"BPJS JKK Employer Expense - {company_abbr}"
            elif "JKM" in component_name:
                return f"BPJS JKM Employer Expense - {company_abbr}"
            else:
                return f"BPJS Expenses - {company_abbr}"
        else:
            # For credit entries, use liability accounts
            if "Kesehatan" in component_name:
                return f"BPJS Kesehatan Payable - {company_abbr}"
            elif "JHT" in component_name:
                return f"BPJS JHT Payable - {company_abbr}"
            elif "JP" in component_name:
                return f"BPJS JP Payable - {company_abbr}"
            elif "JKK" in component_name:
                return f"BPJS JKK Payable - {company_abbr}"
            elif "JKM" in component_name:
                return f"BPJS JKM Payable - {company_abbr}"
            else:
                return f"BPJS Payable - {company_abbr}"
    except Exception as e:
        frappe.logger().error(f"Error getting fallback BPJS account: {str(e)}")
        return None

def get_default_payable_account(doc):
    """
    Get default payable account for salary slip with multiple fallbacks
    
    Args:
        doc (obj): Salary Slip document
        
    Returns:
        str: Default payable account
    """
    try:
        company = getattr(doc, 'company', None)
        if not company:
            return None
            
        # Try direct payroll_payable_account from doc
        payable_account = getattr(doc, 'payroll_payable_account', None)
        
        # Try custom fields
        if not payable_account:
            if hasattr(doc, 'custom_payable_account'):
                payable_account = doc.custom_payable_account
            elif hasattr(doc, 'payable_account'):
                payable_account = doc.payable_account
        
        # Try payroll entry payable account
        if not payable_account and hasattr(doc, 'payroll_entry') and doc.payroll_entry:
            payable_account = frappe.db.get_value(
                'Payroll Entry',
                doc.payroll_entry,
                'payroll_payable_account'
            )
            
        # Try company default payroll payable account
        if not payable_account:
            payable_account = get_default_account(company, "default_payroll_payable_account")
            
        # Fallback to default payable account
        if not payable_account:
            payable_account = get_default_account(company, "default_payable_account")
            
        # Ultimate fallback to standard naming 
        if not payable_account:
            abbr = frappe.get_cached_value('Company', company, 'abbr')
            payable_account = f"Salary Payable - {abbr}"
            
        return payable_account
    except Exception as e:
        frappe.logger().error(f"Error getting default payable account: {str(e)}")
        return None

def get_default_account(company, account_type=None):
    """
    Get default account for company based on account type
    
    Args:
        company (str): Company name
        account_type (str, optional): Account type field in Company document
        
    Returns:
        str: Default account or None
    """
    try:
        if account_type:
            return frappe.get_cached_value('Company', company, account_type)
        return None
    except Exception as e:
        frappe.logger().error(f"Error getting default account for {company}: {str(e)}")
        return None

@frappe.whitelist()
def diagnose_gl_entries(document_name, document_type="Salary Slip"):
    """
    Diagnostic function to analyze GL entries for a document
    
    Args:
        document_name (str): Name of the document
        document_type (str): Type of document (Salary Slip, Payment Entry, Journal Entry)
        
    Returns:
        dict: Diagnostic information about GL entries
    """
    try:
        # Get the document
        doc = frappe.get_doc(document_type, document_name)
        
        result = {
            "name": doc.name,
            "doctype": doc.doctype,
            "company": getattr(doc, "company", None),
            "has_gl_entries": False,
            "gl_entries_count": 0,
            "bpjs_entries": [],
            "bpjs_components": [],
            "accounts_used": []
        }
        
        # Check if document has GL entries
        if hasattr(doc, "gl_entries") and doc.gl_entries:
            result["has_gl_entries"] = True
            result["gl_entries_count"] = len(doc.gl_entries)
            
            # Find BPJS-related entries
            for entry in doc.gl_entries:
                account = getattr(entry, "account", "")
                against = getattr(entry, "against", "")
                
                if "BPJS" in account or "BPJS" in against:
                    result["bpjs_entries"].append({
                        "account": account,
                        "against": against,
                        "debit": getattr(entry, "debit", 0),
                        "credit": getattr(entry, "credit", 0)
                    })
                    
                    # Add unique accounts
                    if account not in result["accounts_used"]:
                        result["accounts_used"].append(account)
                
                # Check for BPJS components in against field
                if "BPJS" in against and against not in result["bpjs_components"]:
                    result["bpjs_components"].append(against)
                    
        # Additional checks for Payment Entry
        if document_type == "Payment Entry":
            # Check references
            if hasattr(doc, "references") and doc.references:
                result["references"] = []
                for ref in doc.references:
                    result["references"].append({
                        "reference_doctype": getattr(ref, "reference_doctype", ""),
                        "reference_name": getattr(ref, "reference_name", ""),
                        "allocated_amount": getattr(ref, "allocated_amount", 0)
                    })
                    
        # Additional checks for Journal Entry
        if document_type == "Journal Entry":
            # Check accounts
            if hasattr(doc, "accounts") and doc.accounts:
                result["journal_accounts"] = []
                for acc in doc.accounts:
                    result["journal_accounts"].append({
                        "account": getattr(acc, "account", ""),
                        "reference_type": getattr(acc, "reference_type", ""),
                        "reference_name": getattr(acc, "reference_name", ""),
                        "debit": getattr(acc, "debit", 0),
                        "credit": getattr(acc, "credit", 0)
                    })
        
        return result
    except Exception as e:
        return {
            "error": str(e),
            "traceback": frappe.get_traceback(),
            "msg": f"Error diagnosing GL entries for {document_type} {document_name}"
        }