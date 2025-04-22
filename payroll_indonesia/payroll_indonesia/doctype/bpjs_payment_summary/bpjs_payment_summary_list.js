frappe.listview_settings['BPJS Payment Summary'] = {
    add_fields: ["status", "total", "payment_entry"],
    
    get_indicator: function(doc) {
        if (doc.status === "Draft") {
            return [__("Draft"), "red", "status,=,Draft"];
        } else if (doc.status === "Submitted") {
            return [__("Submitted"), "blue", "status,=,Submitted"];
        } else if (doc.status === "Paid") {
            return [__("Paid"), "green", "status,=,Paid"];
        }
    },
    
    formatters: {
        total: function(value) {
            return format_currency(value);
        }
    }
};