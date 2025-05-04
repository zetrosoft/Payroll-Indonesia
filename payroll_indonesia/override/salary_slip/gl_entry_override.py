# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-04 03:02:55 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt, cstr

def override_salary_slip_gl_entries(doc, method=None):
    """
    Override GL entries for BPJS components in Salary Slip
    
    This function modifies GL entries for BPJS employer and employee components
    to use correct accounts from BPJS Account Mapping with standardized naming.
    
    Args:
        doc (obj): Salary Slip document
        method (str, optional): Method that called this function
    """
    # Skip if no earnings/deductions
    if not doc.earnings and not doc.deductions:
        return
    
    # Get BPJS account mapping for this company
    bpjs_mapping = get_bpjs_account_mapping(doc.company)
    if not bpjs_mapping:
        frappe.msgprint(_("BPJS Account Mapping not found for company {0}. Using default accounts.").format(doc.company))
        return
    
    # Get existing GL entries that will be created
    gl_entries = get_existing_gl_entries(doc)
    if not gl_entries:
        return
    
    # Log for debugging
    frappe.logger().debug(f"Overriding GL entries for Salary Slip {doc.name} in company {doc.company}")
    
    # Modify GL entries for BPJS components
    modified_entries = []
    
    for entry in gl_entries:
        # Skip entries without 'against' field
        if not entry.get('against'):
            modified_entries.append(entry)
            continue
        
        # Check if this is a BPJS component
        component = entry.get('against')
        if "BPJS" not in component:
            modified_entries.append(entry)
            continue
        
        # Process the component based on standardized naming conventions
        modified_entry = process_bpjs_component_entry(entry, component, bpjs_mapping)
        modified_entries.append(modified_entry)
    
    # Replace GL entries with our modified entries
    doc.gl_entries = modified_entries
    
    # Add debug log for tracing
    if frappe.conf.get("developer_mode"):
        frappe.logger().debug(f"Modified GL entries for {doc.name}: {modified_entries}")

def process_bpjs_component_entry(entry, component, bpjs_mapping):
    """
    Process a GL entry for a BPJS component to use correct accounts
    
    Args:
        entry (dict): Original GL entry
        component (str): BPJS component name
        bpjs_mapping (obj): BPJS Account Mapping document
        
    Returns:
        dict: Modified GL entry with updated account
    """
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
        
        if mapping_dict:
            # Convert back to document
            mapping = frappe.get_doc("BPJS Account Mapping", mapping_dict.get("name"))
            if mapping:
                return mapping
        
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
            frappe.logger().warning(f"Could not create BPJS Account Mapping for {company}")
    
    except Exception as e:
        frappe.logger().error(f"Error getting BPJS Account Mapping for {company}: {str(e)}")
    
    return None

def get_existing_gl_entries(doc):
    """
    Get GL entries that would be created for this Salary Slip
    This simulates the standard ERPNext GL entry creation process
    
    Args:
        doc (obj): Salary Slip document
        
    Returns:
        list: List of GL entries
    """
    gl_entries = []
    
    # Process earnings and statistical components
    for earning in doc.earnings:
        if not earning.salary_component:
            continue
            
        # Get account based on component and type
        account = get_component_account(earning.salary_component, "earnings", doc.company)
        if not account:
            continue
            
        # Create debit entry
        gl_entries.append({
            "account": account,
            "against": earning.salary_component,
            "debit": flt(earning.amount),
            "credit": 0,
            "cost_center": doc.cost_center,
            "project": doc.project
        })
        
        # For statistical components, create balancing credit entry
        if earning.statistical_component == 1:
            default_payable = get_default_payable_account(doc)
            gl_entries.append({
                "account": default_payable,
                "against": earning.salary_component,
                "debit": 0,
                "credit": flt(earning.amount),
                "cost_center": doc.cost_center,
                "project": doc.project
            })
    
    # Process deductions (except loans)
    for deduction in doc.deductions:
        if not deduction.salary_component:
            continue
        
        # Handle loan repayments separately
        if deduction.is_loan_repayment:
            continue
            
        # Get account based on component and type
        account = get_component_account(deduction.salary_component, "deductions", doc.company)
        if not account:
            continue
            
        # Create credit entry
        gl_entries.append({
            "account": account,
            "against": deduction.salary_component,
            "debit": 0,
            "credit": flt(deduction.amount),
            "cost_center": doc.cost_center,
            "project": doc.project
        })
        
        # For statistical components, create balancing debit entry
        if deduction.statistical_component == 1:
            default_payable = get_default_payable_account(doc)
            gl_entries.append({
                "account": default_payable,
                "against": deduction.salary_component,
                "debit": flt(deduction.amount),
                "credit": 0,
                "cost_center": doc.cost_center,
                "project": doc.project
            })
    
    return gl_entries

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
    
    return None

def get_default_payable_account(doc):
    """
    Get default payable account for salary slip
    
    Args:
        doc (obj): Salary Slip document
        
    Returns:
        str: Default payable account
    """
    payable_account = doc.payroll_payable_account
    
    if not payable_account:
        payable_account = get_default_account(doc.company, "default_payroll_payable_account")
        
    if not payable_account:
        # Fallback to default payable account
        payable_account = get_default_account(doc.company, "default_payable_account")
        
    return payable_account

def get_default_account(company, account_type=None):
    """
    Get default account for company based on account type
    
    Args:
        company (str): Company name
        account_type (str, optional): Account type field in Company document
        
    Returns:
        str: Default account or None
    """
    if account_type:
        return frappe.get_cached_value('Company', company, account_type)
    return None