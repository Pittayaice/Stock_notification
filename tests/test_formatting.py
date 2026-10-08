from app import formatting as fmt


def test_price_keeps_two_to_four_decimals():
    assert fmt.price(33.9, "฿") == "฿33.90"
    assert fmt.price(34.266667, "฿") == "฿34.2667"
    assert fmt.price(231.39999389648438, "$") == "$231.40"
    assert fmt.price(1234.5, "$") == "$1,234.50"


def test_qty():
    assert fmt.qty(1000) == "1,000"
    assert fmt.qty(0.5) == "0.5"


def test_signed_money_and_pct():
    assert fmt.signed_money(85, "฿") == "+฿85.00"
    assert fmt.signed_money(-170, "฿") == "-฿170.00"
    assert fmt.signed_money(-0.001, "฿") == "+฿0.00"
    assert fmt.signed_pct(-1.438) == "-1.44%"
    assert fmt.signed_pct(-0.001) == "+0.00%"

