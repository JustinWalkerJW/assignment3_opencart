"""Visible-UI page helpers. No direct cart API calls or hard-coded cart keys."""

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from selenium.common.exceptions import (
    NoSuchElementException, StaleElementReferenceException, TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from cart_tests.data import CART_URL, EMPTY_MESSAGE, PRODUCTS


class SetupIssue(RuntimeError):
    """The specified starting data/environment is unavailable; not a test failure."""


def money(text):
    """Parse the site's displayed dollar format using exact decimal arithmetic."""
    normalized = " ".join(text.split())
    if not re.fullmatch(r"\$\s*(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}", normalized):
        raise ValueError(f"Unexpected money display: {text!r}")
    return Decimal(normalized.replace("$", "").replace(",", "").strip())


def product_id(href):
    values = parse_qs(urlparse(href or "").query).get("product_id", [])
    return int(values[0]) if values and values[0].isdigit() else None


@dataclass(frozen=True)
class CartRow:
    product_id: int
    name: str
    model: str
    quantity: str
    unit_price: Decimal
    line_total: Decimal
    options: tuple = ()


@dataclass(frozen=True)
class CartState:
    rows: tuple
    total: Decimal | None
    empty_message: bool
    stock_warning: bool = False


class Shop:
    def __init__(self, driver, timeout=20):
        self.driver = driver
        self.timeout = timeout
        self.wait = WebDriverWait(
            driver, timeout, poll_frequency=0.25,
            ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
        )

    def visible(self, by, value, root=None):
        root = self.driver if root is None else root
        return [e for e in root.find_elements(by, value) if e.is_displayed()]

    def one(self, by, value, root=None):
        """Fail visibly if a locator becomes ambiguous instead of clicking blindly."""
        def find(_):
            elements = self.visible(by, value, root)
            if len(elements) > 1:
                raise RuntimeError(f"Ambiguous visible locator ({len(elements)}): {value}")
            return elements[0] if elements else False
        return self.wait.until(find, f"No visible element: {value}")

    def content(self):
        return self.driver.find_element(By.ID, "content")

    def open_cart(self):
        self.driver.get(CART_URL)
        self.one(By.ID, "content")

    def set_us_dollars(self):
        """Choose the observed USD menu item; preserve an explicit currency baseline."""
        old_content = self.content()
        self.one(By.CSS_SELECTOR, '#form-currency button.dropdown-toggle').click()
        self.one(By.CSS_SELECTOR, '#form-currency button[name="USD"]').click()
        self.wait.until(EC.staleness_of(old_content))
        self.one(By.ID, "content")
        if not self.one(By.CSS_SELECTOR, '#form-currency button.dropdown-toggle').text.strip().startswith("$"):
            raise SetupIssue("Could not establish the US Dollar currency baseline")

    def open_product(self, pid):
        self.driver.get(PRODUCTS[pid].url)
        self.one(By.ID, "input-quantity")
        if product_id(self.driver.current_url) != pid:
            raise SetupIssue(f"Expected product_id={pid}; URL={self.driver.current_url}")

    def check_product(self, pid, minimum_qty=1):
        """Preconditions belong to fixture setup, so changed catalog data is Error."""
        self.open_product(pid)
        p = PRODUCTS[pid]
        heading = self.one(By.CSS_SELECTOR, "#content h1").text.strip()
        if heading != p.name:
            raise SetupIssue(f"Product {pid}: expected name {p.name!r}, found {heading!r}")
        model = self.one(By.XPATH,
            "//*[@id='content']//li[starts-with(normalize-space(.),'Product Code:')]").text
        if model.split(":", 1)[1].strip() != p.model:
            raise SetupIssue(f"Product {pid}: model changed: {model}")
        stock = self.one(By.XPATH,
            "//*[@id='content']//li[starts-with(normalize-space(.),'Availability:')]").text
        availability = stock.split(":", 1)[1].strip()
        if availability.isdigit():
            if int(availability) < minimum_qty:
                raise SetupIssue(f"Product {pid}: only {availability} available; need {minimum_qty}")
        elif availability.casefold() != "in stock":
            raise SetupIssue(f"Product {pid}: unavailable for this scenario: {availability}")
        # The live price is an h2 inside a list item. A crossed-out original price
        # is a span, and the review heading is outside a list item.
        current = money(self.one(By.CSS_SELECTOR, "#content li h2").text)
        if current != p.unit_price:
            raise SetupIssue(f"Product {pid}: expected current price {p.unit_price}; found {current}")
        if p.option_id:
            self.check_select_precondition(pid)
        elif self.visible(By.CSS_SELECTOR, "#product .required"):
            raise SetupIssue(f"Product {pid}: unexpected required option; revise the baseline")

    def set_product_quantity(self, value):
        field = self.one(By.ID, "input-quantity")
        field.clear()
        field.send_keys(str(value))

    def click_add(self):
        self.one(By.ID, "button-cart").click()

    def success_alerts(self, pid):
        expected = f"Success: You have added {PRODUCTS[pid].name} to your shopping cart!"
        return [e for e in self.visible(By.CSS_SELECTOR, '[role="alert"], .alert-success')
                if expected in " ".join(e.text.split())]

    def expect_added(self, pid):
        try:
            return self.wait.until(lambda _: self.success_alerts(pid))[0]
        except TimeoutException as exc:
            raise AssertionError(f"No success notification for product {pid}") from exc

    def add_product(self, pid, quantity):
        self.open_product(pid)
        p = PRODUCTS[pid]
        if p.option_id:
            Select(self.one(By.ID, p.option_id)).select_by_value(p.option_value)
        self.set_product_quantity(quantity)
        self.click_add()
        self.expect_added(pid)

    def required_select(self, pid=30):
        return self.one(By.ID, PRODUCTS[pid].option_id)

    def check_select_precondition(self, pid=30):
        select = self.required_select(pid)
        ancestors = select.find_elements(By.XPATH,
            "./ancestor::*[contains(concat(' ',normalize-space(@class),' '),' required ')]")
        labels = self.driver.find_elements(By.CSS_SELECTOR, f'label[for="{select.get_attribute("id")}"]')
        required = bool(ancestors) or select.get_attribute("required") is not None
        required = required or any("*" in label.text for label in labels)
        if not required:
            raise SetupIssue("Select is no longer marked required; review the Canon scenarios")
        options = Select(select).options
        if not any(o.get_attribute("value") == "" for o in options):
            raise SetupIssue("Required Select placeholder is unavailable")
        p = PRODUCTS[pid]
        match = [o for o in options if o.get_attribute("value") == p.option_value
                 and o.text.strip() == p.option_label and o.is_enabled()]
        if len(match) != 1:
            raise SetupIssue(f"Expected Select option {p.option_label!r} is unavailable or changed")

    def leave_select_empty(self):
        Select(self.required_select()).select_by_value("")
        assert self.required_select().get_attribute("value") == "", "Select was not left empty"

    def expect_select_error(self):
        try:
            error = self.wait.until(lambda _: self.visible(By.XPATH,
                "//*[@id='content']//*[normalize-space(.)='Select required!']"))[-1]
        except TimeoutException as exc:
            raise AssertionError("Missing required-option error: Select required!") from exc
        assert not self.success_alerts(30), "Canon success appeared despite the empty required Select"
        return error

    def cart_table(self):
        """Use the full cart's headers; hidden mini-cart rows must not enter assertions."""
        matches = []
        for table in self.visible(By.TAG_NAME, "table", self.content()):
            headers = [e.text.strip() for e in table.find_elements(By.CSS_SELECTOR, "thead tr > *")]
            if "Model" in headers and "Quantity" in headers:
                matches.append((table, headers))
        if len(matches) > 1:
            raise RuntimeError("Multiple visible main cart tables")
        return matches[0] if matches else (None, [])

    def row_id(self, row):
        ids = {product_id(a.get_attribute("href"))
               for a in row.find_elements(By.CSS_SELECTOR, 'a[href*="product_id="]')}
        ids.discard(None)
        if len(ids) != 1:
            raise RuntimeError(f"Cannot identify cart row by exact product_id: {ids}")
        return ids.pop()

    def snapshot(self):
        main = self.content()
        empty = bool(self.visible(By.XPATH, f".//*[normalize-space(.)='{EMPTY_MESSAGE}']", main))
        stock_warning = any("not available in the desired quantity or not in stock" in e.text
                            for e in self.visible(By.CSS_SELECTOR, ".alert-danger"))
        table, headers = self.cart_table()
        if table is None:
            return CartState((), None, True, stock_warning) if empty else None
        positions = {label: headers.index(label) for label in
                     ("Product Name", "Model", "Quantity", "Unit Price", "Total")}
        rows = []
        for row in table.find_elements(By.CSS_SELECTOR, "tbody > tr"):
            if not row.is_displayed():
                continue
            cells = row.find_elements(By.XPATH, "./td")
            if not cells:
                continue
            pid = self.row_id(row)
            name_cell = cells[positions["Product Name"]]
            links = [a for a in name_cell.find_elements(By.TAG_NAME, "a")
                     if product_id(a.get_attribute("href")) == pid and a.text.strip()]
            if len(links) != 1:
                raise RuntimeError(f"Cannot read product name in cart row {pid}")
            quantity = row.find_element(By.CSS_SELECTOR, 'input[name^="quantity["]').get_attribute("value")
            stock_warning = stock_warning or "***" in name_cell.text
            options = tuple(sorted(e.text.strip() for e in name_cell.find_elements(By.TAG_NAME, "small")
                                   if e.text.strip() and not e.text.strip().startswith("Reward Points:")))
            rows.append(CartRow(pid, links[0].text.strip(), cells[positions["Model"]].text.strip(),
                                quantity, money(cells[positions["Unit Price"]].text),
                                money(cells[positions["Total"]].text), options))
        totals = []
        for row in main.find_elements(By.CSS_SELECTOR, "table tr"):
            cells = row.find_elements(By.XPATH, "./td")
            if row.is_displayed() and len(cells) == 2 and cells[0].text.strip().rstrip(":") == "Total":
                totals.append(money(cells[1].text))
        if len(totals) != 1:
            return None  # The AJAX replacement can briefly leave no totals table.
        return CartState(tuple(sorted(rows, key=lambda r: r.product_id)), totals[0], empty, stock_warning)

    def expect_cart(self, quantities):
        """Wait for quantity AND prices AND total, not merely an edited input value."""
        expected_rows = tuple(
            CartRow(pid, PRODUCTS[pid].name, PRODUCTS[pid].model, str(qty),
                    PRODUCTS[pid].unit_price, PRODUCTS[pid].unit_price * qty, PRODUCTS[pid].cart_options)
            for pid, qty in sorted(quantities.items())
        )
        expected = CartState(expected_rows,
                             sum((r.line_total for r in expected_rows), Decimal("0.00"))
                             if expected_rows else None, not bool(expected_rows))
        last = None

        def matches(_):
            nonlocal last
            state = self.snapshot()
            if state is not None:
                last = state
            return state if state == expected else False

        try:
            return self.wait.until(matches)
        except TimeoutException as exc:
            if last is None:
                raise TimeoutException("Could not read a complete main cart; check page/locators/network.") from exc
            raise AssertionError(f"Cart mismatch after {self.timeout}s.\nExpected: {expected}\nActual: {last}") from exc

    def row_element(self, pid):
        def find(_):
            table, _headers = self.cart_table()
            if table is None:
                return False
            rows = [row for row in table.find_elements(By.CSS_SELECTOR, "tbody > tr")
                    if row.is_displayed() and self.row_id(row) == pid]
            if len(rows) > 1:
                raise AssertionError(f"Duplicate rows for product {pid}")
            return rows[0] if rows else False
        return self.wait.until(find, f"No cart row for product {pid}")

    def enter_cart_quantity(self, pid, quantity):
        field = self.row_element(pid).find_element(By.CSS_SELECTOR, 'input[name^="quantity["]')
        field.clear()
        field.send_keys(str(quantity))
        assert field.get_attribute("value") == str(quantity), "Quantity entry was not retained"

    def click_update(self, pid):
        self.row_element(pid).find_element(By.CSS_SELECTOR,
            'button[data-original-title="Update"], button[title="Update"]').click()

    def remove(self, pid):
        self.row_element(pid).find_element(By.CSS_SELECTOR,
            'button[data-original-title="Remove"], button[title="Remove"]').click()

    def expect_continue(self):
        try:
            self.one(By.XPATH, ".//a[normalize-space(.)='Continue']", self.content())
        except TimeoutException as exc:
            raise AssertionError("Empty cart has no visible Continue link") from exc

    def refresh_and_expect(self, quantities):
        self.driver.refresh()
        return self.expect_cart(quantities)

    def cleanup(self):
        """Delete only scenario products in this new guest session, after evidence."""
        self.open_cart()
        state = self.wait.until(lambda _: self.snapshot())
        for pid in {row.product_id for row in state.rows}:
            if pid not in PRODUCTS:
                raise RuntimeError(f"Unexpected product {pid}; cleanup will not remove it")
            self.remove(pid)
            self.wait.until(lambda _: (s := self.snapshot()) is not None
                            and all(row.product_id != pid for row in s.rows))
        self.expect_cart({})
