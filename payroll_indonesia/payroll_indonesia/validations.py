import frappe
from frappe import _


@frappe.whitelist()
def validate_employee_golongan(jabatan, golongan):
    """
    Validate that employee's golongan level does not exceed the maximum allowed for their jabatan

    Args:
        jabatan (str): The jabatan (position) code
        golongan (str): The golongan (grade) code

    Raises:
        frappe.ValidationError: If golongan level exceeds maximum allowed level
    """
    if not jabatan:
        frappe.throw(_("Jabatan is required"))

    if not golongan:
        frappe.throw(_("Golongan is required"))

    max_golongan = frappe.db.get_value("Jabatan", jabatan, "max_golongan")
    if not max_golongan:
        frappe.throw(_("Maximum Golongan not set for Jabatan {0}").format(jabatan))

    max_level = frappe.db.get_value("Golongan", max_golongan, "level")
    if not max_level:
        frappe.throw(_("Level not set for Golongan {0}").format(max_golongan))

    current_level = frappe.db.get_value("Golongan", golongan, "level")
    if not current_level:
        frappe.throw(_("Level not set for Golongan {0}").format(golongan))

    if current_level > max_level:
        frappe.throw(
            _(
                "Employee's Golongan level ({0}) cannot be higher than "
                "the maximum allowed level ({1}) for the selected Jabatan"
            ).format(current_level, max_level)
        )
