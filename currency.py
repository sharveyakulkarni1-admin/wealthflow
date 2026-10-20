from decimal import Decimal, ROUND_HALF_UP

# Mock centralized rates relative to USD. Replace this dictionary with a
# provider-backed cache when connecting a live FX service.
RATES_TO_USD = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "INR": Decimal("0.0120"),
}


def convert(amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
    if from_currency == to_currency:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    usd = amount * RATES_TO_USD[from_currency]
    result = usd / RATES_TO_USD[to_currency]
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
