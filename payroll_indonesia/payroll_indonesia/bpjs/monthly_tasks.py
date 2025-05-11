import frappe
from frappe import _
from frappe.utils import getdate, get_first_day, get_last_day, add_months


def create_bpjs_summaries():
    """Create monthly BPJS Payment Summaries"""
    try:
        # Get previous month
        today = getdate()
        first_day = get_first_day(add_months(today, -1))
        last_day = get_last_day(first_day)

        # Get all companies
        companies = frappe.get_all("Company", pluck="name")

        for company in companies:
            # Check if summary already exists
            existing = frappe.db.exists(
                "BPJS Payment Summary",
                {"company": company, "start_date": first_day, "end_date": last_day},
            )

            if not existing:
                try:
                    # Create new summary
                    summary = frappe.new_doc("BPJS Payment Summary")
                    summary.company = company
                    summary.start_date = first_day
                    summary.end_date = last_day
                    summary.generate_from_salary_slips()
                    summary.insert()

                    frappe.logger().info(
                        f"Created BPJS Payment Summary for {company} - {first_day}"
                    )
                except Exception as e:
                    frappe.logger().error(
                        f"Error creating BPJS Payment Summary for {company}: {str(e)}"
                    )
                    continue

        frappe.logger().info("Completed monthly BPJS summary creation")

    except Exception as e:
        frappe.log_error(
            f"Error in monthly BPJS summary creation: {str(e)}", "BPJS Monthly Task Error"
        )
