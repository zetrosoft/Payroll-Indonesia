import frappe
from frappe import _

@frappe.whitelist()
def validate_employee_golongan(jabatan, golongan):
    if not (jabatan and golongan):
        return
        
    max_golongan = frappe.db.get_value('Jabatan', jabatan, 'max_golongan')
    if not max_golongan:
        return
        
    max_level = frappe.db.get_value('Golongan', max_golongan, 'level')
    current_level = frappe.db.get_value('Golongan', golongan, 'level')
    
    if current_level > max_level:
        frappe.throw(
            _("Employee's Golongan level ({0}) cannot be higher than "
              "the maximum allowed level ({1}) for the selected Jabatan")
            .format(current_level, max_level)
        )
