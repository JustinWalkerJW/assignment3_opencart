"""T008 / F8 - Update Cart Quantity. Tester: Hanlin Yu."""

import pytest


@pytest.mark.scenario(id="T008-S1", function="F8", cart={41: 1}, required_stock={41: 3})
def test_T008_S1_increase_quantity(shop, evidence):
    """Increase 1 to 3; verify $366.00 and persistence after a fresh page load."""
    evidence.cart(shop, "before_increase")
    evidence.record("update_quantity", product_id=41, old=1, new=3)
    shop.enter_cart_quantity(41, 3)
    shop.click_update(41)
    shop.expect_cart({41: 3})
    evidence.cart(shop, "after_increase")
    shop.refresh_and_expect({41: 3})
    evidence.cart(shop, "increase_persists_after_refresh")


@pytest.mark.scenario(id="T008-S2", function="F8", cart={41: 3})
def test_T008_S2_decrease_quantity(shop, evidence):
    """Decrease 3 to 1; preserve the product and restore the $122.00 total."""
    evidence.cart(shop, "before_decrease")
    evidence.record("update_quantity", product_id=41, old=3, new=1)
    shop.enter_cart_quantity(41, 1)
    shop.click_update(41)
    shop.expect_cart({41: 1})
    evidence.cart(shop, "after_decrease")
    shop.refresh_and_expect({41: 1})
    evidence.cart(shop, "decrease_persists_after_refresh")


@pytest.mark.scenario(id="T008-S3", function="F8", cart={41: 1})
def test_T008_S3_zero_quantity_removes_item(shop, evidence):
    """Characterization assumption: zero removes the row; not a normative rule."""
    evidence.cart(shop, "before_zero")
    evidence.record("update_quantity", product_id=41, old=1, new=0,
                    basis="Observed regression assumption; no independent zero-quantity specification")
    shop.enter_cart_quantity(41, 0)
    evidence.capture("zero_entered_before_update", element=shop.content())
    shop.click_update(41)
    shop.expect_cart({})  # Empty message and no rows; no $0.00 table is required.
    evidence.cart(shop, "after_zero_empty_cart")
    shop.refresh_and_expect({})
    evidence.cart(shop, "zero_removal_persists_after_refresh")
