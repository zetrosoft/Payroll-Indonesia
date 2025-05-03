import frappe

def validate_settings(doc, method=None):
    """Wrapper for BPJSSettings.validate method"""
    # Skip if already being validated
    if getattr(doc, "_validated", False):
        return
        
    # Mark as being validated to prevent recursion
    doc._validated = True
    
    # Call the instance method
    doc.validate_data_types()
    doc.validate_percentages()
    doc.validate_max_salary()
    doc.validate_account_types()
    
    # Clean up flag
    doc._validated = False
    
def setup_accounts(doc, method=None):
    """Wrapper for BPJSSettings.setup_accounts method"""
    # Skip if already being processed
    if getattr(doc, "_setup_running", False):
        return
        
    # Mark as being processed to prevent recursion
    doc._setup_running = True
    
    # Call the instance method
    doc.setup_accounts()
    
    # Clean up flag
    doc._setup_running = False