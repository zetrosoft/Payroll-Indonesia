# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import getdate, add_months, get_first_day, get_last_day, flt
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter
# from payroll_indonesia.override.salary_slip.gl_entry_override import make_gl_entries


class TestPayrollIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Setup test environment"""
        cls.setup_company()
        cls.setup_test_employees()

    @classmethod
    def tearDownClass(cls):
        """Cleanup test data"""
        frappe.db.rollback()

    @classmethod
    def setup_company(cls):
        """Setup test company with required accounts"""
        # Check if company already exists
        if frappe.db.exists("Company", "Test Payroll Company"):
            # Fetch existing company
            cls.company = frappe.get_doc("Company", "Test Payroll Company")
        else:
            # Create new company
            cls.company = frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": "Test Payroll Company",
                    "country": "Indonesia",
                    "default_currency": "IDR",
                    "abbr": "TPC",
                    "domain": "Manufacturing",
                }
            )
            cls.company.insert()

        # Setup accounts
        accounts = [
            {"account_name": "BPJS Payable", "account_type": "Payable"},
            {"account_name": "PPh 21 Payable", "account_type": "Payable"},
            {"account_name": "Payroll Payable", "account_type": "Payable"},
            {"account_name": "Salary", "account_type": "Expense"},
        ]

        for acc in accounts:
            account_name = f"{acc['account_name']} - {cls.company.abbr}"
            if not frappe.db.exists("Account", account_name):
                # Determine parent account based on account type
                parent_account = (
                    f"Accounts Payable - {cls.company.abbr}"
                    if acc["account_type"] == "Payable"
                    else f"Expenses - {cls.company.abbr}"
                )

                # Check if parent account exists
                if not frappe.db.exists("Account", parent_account):
                    frappe.msgprint(
                        f"Parent account {parent_account} does not exist. Skipping {account_name}"
                    )
                    continue

                account = frappe.get_doc(
                    {
                        "doctype": "Account",
                        "account_name": acc["account_name"],
                        "parent_account": parent_account,
                        "account_type": acc["account_type"],
                        "company": cls.company.name,
                    }
                )
                account.insert()

        # Update default accounts only if they're different from current values
        update_needed = False
        default_accounts = {
            "default_payroll_payable_account": f"Payroll Payable - {cls.company.abbr}",
            "default_bpjs_payable_account": f"BPJS Payable - {cls.company.abbr}",
            "default_pph21_payable_account": f"PPh 21 Payable - {cls.company.abbr}",
        }

        for field, account in default_accounts.items():
            # Only update if account exists and current value differs
            if frappe.db.exists("Account", account) and cls.company.get(field) != account:
                cls.company.set(field, account)
                update_needed = True

        # Save only if changes were made
        if update_needed:
            cls.company.save()

    @classmethod
    def setup_test_employees(cls):
        """Create test employees with different configurations"""
        cls.test_employees = {
            "ter_with_bpjs": cls.create_test_employee(
                "TER with BPJS",
                {
                    "status_pajak": "K0",
                    "override_tax_method": "TER",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                },
            ),
            "progressive_with_bpjs": cls.create_test_employee(
                "Progressive with BPJS",
                {
                    "status_pajak": "K0",
                    "override_tax_method": "Progressive",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                },
            ),
            "ter_no_bpjs": cls.create_test_employee(
                "TER no BPJS",
                {
                    "status_pajak": "K0",
                    "override_tax_method": "TER",
                    "ikut_bpjs_kesehatan": 0,
                    "ikut_bpjs_ketenagakerjaan": 0,
                },
            ),
        }

    @classmethod
    def create_test_employee(cls, name_suffix, config):
        """Create test employee with given configuration"""
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Test {name_suffix}",
                "last_name": "Employee",
                "status": "Active",
                "company": cls.company.name,
                "date_of_birth": add_months(getdate(), -(30 * 12)),  # 30 years old
                "date_of_joining": add_months(getdate(), -12),
                "department": "All Departments",
                "gender": "Male",
                "npwp": "123456789012345",
                # Configuration from params
                "status_pajak": config.get("status_pajak", "TK0"),
                "override_tax_method": config.get("override_tax_method", ""),
                "ikut_bpjs_kesehatan": config.get("ikut_bpjs_kesehatan", 1),
                "ikut_bpjs_ketenagakerjaan": config.get("ikut_bpjs_ketenagakerjaan", 1),
            }
        )
        employee.insert()
        return employee

    def create_payroll_entry(self, posting_date):
        """Create test payroll entry"""
        start_date = get_first_day(posting_date)
        end_date = get_last_day(posting_date)

        payroll_entry = frappe.get_doc(
            {
                "doctype": "Payroll Entry",
                "company": self.company.name,
                "posting_date": posting_date,
                "payroll_frequency": "Monthly",
                "start_date": start_date,
                "end_date": end_date,
                "payment_account": f"Cash - {self.company.abbr}",
                # Add the missing mandatory fields
                "exchange_rate": 1.0,
                "payroll_payable_account": self.company.default_payroll_payable_account,
                # Set other useful fields
                "currency": self.company.default_currency,
                "cost_center": self.get_or_create_cost_center(),
            }
        )

        # Add employees
        for employee in self.test_employees.values():
            payroll_entry.append(
                "employees", {"employee": employee.name, "base_gross_pay": 15000000}  # 15 juta
            )

        payroll_entry.insert()
        return payroll_entry

    def get_or_create_cost_center(self):
        """Get or create a cost center for the company"""
        cost_center_name = f"Main - {self.company.abbr}"

        if not frappe.db.exists("Cost Center", cost_center_name):
            # Create cost center
            cost_center = frappe.get_doc(
                {
                    "doctype": "Cost Center",
                    "cost_center_name": "Main",
                    "company": self.company.name,
                    "is_group": 0,
                    "parent_cost_center": f"{self.company.name} - {self.company.abbr}",
                }
            )

            try:
                cost_center.insert()
                return cost_center.name
            except frappe.exceptions.DuplicateEntryError:
                # In case another process created it
                return cost_center_name

        return cost_center_name

    def test_ter_with_bpjs_december(self):
        """Test TER calculation with BPJS in December"""
        # Create December payroll entry
        december_date = getdate("2025-12-15")
        payroll_entry = self.create_payroll_entry(december_date)

        # Create salary slip
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employees["ter_with_bpjs"].name,
                "posting_date": december_date,
                "start_date": get_first_day(december_date),
                "end_date": get_last_day(december_date),
                "company": self.company.name,
                "payroll_entry": payroll_entry.name,
            }
        )

        # Set test earnings
        salary_slip.append("earnings", {"salary_component": "Basic Salary", "amount": 15000000})

        salary_slip.gross_pay = 15000000
        salary_slip.insert()

        # Calculate tax components
        calculate_tax_components(salary_slip)

        # Verify TER calculation
        self.assertTrue(salary_slip.is_using_ter)
        self.assertTrue(salary_slip.ter_rate > 0)
        self.assertTrue(salary_slip.ter_category)

        # Verify BPJS deductions exist
        bpjs_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
        for component in bpjs_components:
            deduction = next(
                (d for d in salary_slip.deductions if d.salary_component == component), None
            )
            self.assertIsNotNone(deduction)
            self.assertTrue(deduction.amount > 0)

        # Verify PPh 21 deduction
        pph21_deduction = next(
            (d for d in salary_slip.deductions if d.salary_component == "PPh 21"), None
        )
        self.assertIsNotNone(pph21_deduction)
        self.assertTrue(pph21_deduction.amount > 0)

        # Verify December correction exists
        self.assertTrue(salary_slip.koreksi_pph21 > 0)

        # Submit salary slip
        salary_slip.submit()

        # Get GL entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": salary_slip.name},
            fields=["account", "debit", "credit"],
        )

        # Verify GL entries
        required_accounts = [
            f"BPJS Payable - {self.company.abbr}",
            f"PPh 21 Payable - {self.company.abbr}",
            f"Payroll Payable - {self.company.abbr}",
            f"Salary - {self.company.abbr}",
        ]

        for account in required_accounts:
            entry = next((e for e in gl_entries if e.account == account), None)
            self.assertIsNotNone(entry, f"Missing GL entry for {account}")

        # Verify total debit equals total credit
        total_debit = sum(flt(e.debit) for e in gl_entries)
        total_credit = sum(flt(e.credit) for e in gl_entries)
        self.assertEqual(flt(total_debit, 2), flt(total_credit, 2))

    def test_progressive_with_bpjs_regular(self):
        """Test Progressive calculation with BPJS in regular month"""
        # Create regular month payroll entry (e.g. May)
        may_date = getdate("2025-05-15")
        payroll_entry = self.create_payroll_entry(may_date)

        # Create salary slip
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employees["progressive_with_bpjs"].name,
                "posting_date": may_date,
                "start_date": get_first_day(may_date),
                "end_date": get_last_day(may_date),
                "company": self.company.name,
                "payroll_entry": payroll_entry.name,
            }
        )

        # Set test earnings
        salary_slip.append("earnings", {"salary_component": "Basic Salary", "amount": 15000000})

        salary_slip.gross_pay = 15000000
        salary_slip.insert()

        # Calculate tax components
        calculate_tax_components(salary_slip)

        # Verify Progressive calculation
        self.assertFalse(salary_slip.is_using_ter)
        self.assertEqual(salary_slip.ter_rate, 0)
        self.assertFalse(salary_slip.ter_category)

        # Verify BPJS deductions
        bpjs_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
        for component in bpjs_components:
            deduction = next(
                (d for d in salary_slip.deductions if d.salary_component == component), None
            )
            self.assertIsNotNone(deduction)
            self.assertTrue(deduction.amount > 0)

        # Verify PPh 21 deduction
        pph21_deduction = next(
            (d for d in salary_slip.deductions if d.salary_component == "PPh 21"), None
        )
        self.assertIsNotNone(pph21_deduction)
        self.assertTrue(pph21_deduction.amount > 0)

        # Verify no December correction in regular month
        self.assertEqual(salary_slip.koreksi_pph21, 0)

        # Submit salary slip
        salary_slip.submit()

        # Verify GL entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": salary_slip.name},
            fields=["account", "debit", "credit"],
        )

        # Verify GL entries balance
        total_debit = sum(flt(e.debit) for e in gl_entries)
        total_credit = sum(flt(e.credit) for e in gl_entries)
        self.assertEqual(flt(total_debit, 2), flt(total_credit, 2))

    def test_ter_without_bpjs(self):
        """Test TER calculation without BPJS enrollment"""
        # Create regular month payroll entry
        test_date = getdate("2025-05-15")
        payroll_entry = self.create_payroll_entry(test_date)

        # Create salary slip
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employees["ter_no_bpjs"].name,
                "posting_date": test_date,
                "start_date": get_first_day(test_date),
                "end_date": get_last_day(test_date),
                "company": self.company.name,
                "payroll_entry": payroll_entry.name,
            }
        )

        # Set test earnings
        salary_slip.append("earnings", {"salary_component": "Basic Salary", "amount": 15000000})

        salary_slip.gross_pay = 15000000
        salary_slip.insert()

        # Calculate tax components
        calculate_tax_components(salary_slip)

        # Verify TER calculation
        self.assertTrue(salary_slip.is_using_ter)
        self.assertTrue(salary_slip.ter_rate > 0)

        # Verify no BPJS deductions
        bpjs_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
        for component in bpjs_components:
            deduction = next(
                (d for d in salary_slip.deductions if d.salary_component == component), None
            )
            self.assertIsNone(deduction)

        # Verify PPh 21 is still calculated
        pph21_deduction = next(
            (d for d in salary_slip.deductions if d.salary_component == "PPh 21"), None
        )
        self.assertIsNotNone(pph21_deduction)
        self.assertTrue(pph21_deduction.amount > 0)

        # Submit salary slip
        salary_slip.submit()

        # Verify GL entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": salary_slip.name},
            fields=["account", "debit", "credit"],
        )

        # Verify no BPJS payable entry
        bpjs_payable = next(
            (e for e in gl_entries if e.account == f"BPJS Payable - {self.company.abbr}"), None
        )
        self.assertIsNone(bpjs_payable)

        # Verify other GL entries exist and balance
        total_debit = sum(flt(e.debit) for e in gl_entries)
        total_credit = sum(flt(e.credit) for e in gl_entries)
        self.assertEqual(flt(total_debit, 2), flt(total_credit, 2))


def run_payroll_integration_tests():
    """Run payroll integration tests"""
    import frappe.test_runner

    test_result = frappe.test_runner.run_tests(
        {
            "tests": [
                {
                    "module_name": "payroll_indonesia.payroll_indonesia.tests.test_payroll_integration",
                    "test_name": "TestPayrollIntegration",
                }
            ]
        }
    )
    return test_result
