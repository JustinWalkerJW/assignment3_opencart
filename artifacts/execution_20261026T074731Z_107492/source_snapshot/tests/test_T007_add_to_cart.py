"""T007 / F7 - Add to Cart. Tester: Hanlin Yu. Three independent scenarios."""

import pytest


@pytest.mark.scenario(id="T007-S1", function="F7", cart={}, product=41)
def test_T007_S1_add_one_valid_product(shop, evidence):
    """Add one P41 to an empty cart; verify notification, row and all amounts."""
    shop.open_product(41)
    shop.set_product_quantity(1)
    evidence.record("add", product_id=41, quantity=1)
    shop.click_add()
    alert = shop.expect_added(41)
    evidence.capture("add_success_notification", element=alert)
    shop.open_cart()
    shop.expect_cart({41: 1})
    evidence.cart(shop, "after_add_one")


@pytest.mark.scenario(id="T007-S2", function="F7", cart={41: 1}, required_stock={41: 2})
def test_T007_S2_merge_duplicate_product(shop, evidence):
    """Add P41 again; one row with two units is required, not two separate rows."""
    evidence.cart(shop, "before_duplicate_add")
    evidence.record("add_again", product_id=41, quantity=1)
    shop.add_product(41, 1)
    shop.open_cart()
    shop.expect_cart({41: 2})
    evidence.cart(shop, "after_duplicate_add")


@pytest.mark.scenario(id="T007-S3", function="F7", cart={41: 1}, product=30)
def test_T007_S3_reject_missing_required_select(shop, evidence):
    """Missing Select must reject P30 while preserving the existing P41 sentinel."""
    evidence.cart(shop, "before_missing_select")
    shop.open_product(30)
    shop.set_product_quantity(1)
    shop.leave_select_empty()
    evidence.record("add_with_missing_select", product_id=30, quantity=1, select="")
    shop.click_add()
    error = shop.expect_select_error()
    evidence.capture("select_required_message", element=error)
    evidence.capture("select_validation_page")
    shop.open_cart()
    shop.expect_cart({41: 1})  # Exact row set also proves P30 was not inserted.
    evidence.cart(shop, "unchanged_cart_after_rejection")
