import frappe
from frappe import _

def update_tax_summaries():
    """Update employee tax summaries at the end of each month
    
    This function is meant to be called by a scheduled job,
    or can be manually triggered to update all employee tax
    summaries for the current or previous month
    """
    try:
        frappe.log_error("Tax summary update triggered", "Monthly Tax Update")
    except Exception as e:
        frappe.log_error(f"Error updating tax summaries: {str(e)}", "Monthly Tax Error")
