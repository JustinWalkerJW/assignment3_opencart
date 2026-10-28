"""T009 / F9 - Remove Cart Item. Tester: Hanlin Yu."""

import pytest


@pytest.mark.scenario(id="T009-S1", function="F9", cart={41: 1})
def test_T009_S1_remove_only_single_unit_item(shop, evidence):
    """Remove the only single-unit item and check the empty-state Continue link."""
    evidence.cart(shop, "before_single_remove")
    evidence.record("remove_once", product_id=41, previous_quantity=1)
    shop.remove(41)
    shop.expect_cart({})
    shop.expect_continue()
    evidence.cart(shop, "after_single_remove")


@pytest.mark.scenario(id="T009-S2", function="F9", cart={41: 1, 30: 1})
def test_T009_S2_remove_one_preserve_other(shop, evidence):
    """Remove P41 from a $220.00 cart; P30 with Select Red must remain at $98.00."""
    evidence.cart(shop, "before_selective_remove")
    evidence.record("remove_once", product_id=41, preserve_product_id=30, preserve_option="Red")
    shop.remove(41)
    shop.expect_cart({30: 1})
    evidence.cart(shop, "after_selective_remove")
    shop.refresh_and_expect({30: 1})
    evidence.cart(shop, "remaining_product_persists_after_refresh")


@pytest.mark.scenario(id="T009-S3", function="F9", cart={41: 3})
def test_T009_S3_remove_whole_multi_unit_row(shop, evidence):
    """A single Remove click deletes all three units, not just one unit."""
    evidence.cart(shop, "before_multi_unit_remove")
    evidence.record("remove_once", product_id=41, previous_quantity=3)
    shop.remove(41)
    shop.expect_cart({})
    evidence.cart(shop, "after_multi_unit_remove")
    shop.refresh_and_expect({})
    evidence.cart(shop, "whole_row_removal_persists_after_refresh")
