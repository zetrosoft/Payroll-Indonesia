frappe.listview_settings['PPh TER Table'] = {
    add_fields: ["title"],
    
    get_indicator: function(doc) {
        return [__(doc.status_pajak), "blue", "status_pajak,=," + doc.status_pajak];
    },
    
    formatter: {
        ter_percent: function(value) {
            return value + '%';
        },
        to_income: function(value) {
            return value === 0 ? '∞' : format_currency(value);
        }
    }
};
