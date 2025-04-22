frappe.ui.form.on('Salary Slip', {
    refresh: function(frm) {
        // Add custom buttons or functionality for Indonesian payroll
        if (frm.doc.custom_status === "Final Gabung Suami") {
            frm.dashboard.add_indicator(__("NPWP Gabung Suami"), "blue");
        }
    }
});