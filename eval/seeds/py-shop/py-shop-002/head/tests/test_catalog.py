from shop.services.catalog import CatalogService


def test_search_matches_part_of_the_name(uow) -> None:
    assert [p.sku for p in CatalogService(uow).search_products("note")] == ["NB-A5"]


def test_search_ignores_surrounding_whitespace(uow) -> None:
    assert [p.sku for p in CatalogService(uow).search_products("  pen ")] == ["PEN-01"]


def test_blank_search_returns_nothing(uow) -> None:
    assert CatalogService(uow).search_products("   ") == []
