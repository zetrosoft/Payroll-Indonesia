import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

class PPhTERTable(Document):
    def autoname(self):
        """Set name as TER-{status_pajak}-{from_income}-{####}"""
        if not self.title:
            self.set_title()
    
    def validate(self):
        self.validate_income_range()
        self.validate_overlapping_range()
        self.set_title()
    
    def set_title(self):
        """Set title for list view display"""
        company = frappe.defaults.get_defaults().get('company')
        currency = frappe.get_cached_value('Company', company, 'default_currency') if company else 'IDR'
        
        to_income_display = "∞" if not self.to_income or self.to_income == 0 else \
            fmt_money(self.to_income, currency=currency)
            
        self.title = "{}: {} - {} @ {}%".format(
            self.status_pajak,
            fmt_money(self.from_income, currency=currency),
            to_income_display,
            self.ter_percent
        )
    
    def validate_income_range(self):
        """Validate that from_income is less than to_income if to_income is not zero"""
        if self.to_income and self.from_income >= self.to_income:
            frappe.throw(
                _("From Income ({0}) must be less than To Income ({1})")
                .format(
                    fmt_money(self.from_income),
                    fmt_money(self.to_income)
                )
            )
    
    def validate_overlapping_range(self):
        """Check for overlapping ranges with the same status_pajak"""
        if not self.from_income:
            return
            
        # Convert 0 to a very large number for comparison
        to_income = self.to_income if self.to_income else 999999999999
        
        overlapping = frappe.db.sql("""
            SELECT name, from_income, to_income, ter_percent
            FROM `tabPPh TER Table`
            WHERE status_pajak = %(status_pajak)s
                AND name != %(name)s
                AND (
                    (%(from_income)s BETWEEN from_income 
                        AND IFNULL(NULLIF(to_income, 0), 999999999999))
                    OR
                    (%(to_income)s BETWEEN from_income 
                        AND IFNULL(NULLIF(to_income, 0), 999999999999))
                    OR
                    (from_income BETWEEN %(from_income)s AND %(to_income)s)
                )
        """, {
            'status_pajak': self.status_pajak,
            'name': self.name or 'New PPh TER Table',
            'from_income': self.from_income,
            'to_income': to_income
        }, as_dict=1)
        
        if overlapping:
            company = frappe.defaults.get_defaults().get('company')
            currency = frappe.get_cached_value('Company', company, 'default_currency') if company else 'IDR'
            
            ranges = []
            for o in overlapping:
                to_income_str = "∞" if not o.to_income or o.to_income == 0 else \
                    fmt_money(o.to_income, currency=currency)
                ranges.append(
                    _("{0}: {1} - {2} @ {3}%").format(
                        o.name,
                        fmt_money(o.from_income, currency=currency),
                        to_income_str,
                        o.ter_percent
                    )
                )
            
            frappe.throw(
                _("Income range overlaps with existing record(s) for status {0}:<br>{1}")
                .format(
                    self.status_pajak,
                    "<br>".join(ranges)
                )
            )
