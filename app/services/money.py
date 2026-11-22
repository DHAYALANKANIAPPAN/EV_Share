from ..config import settings


def split(amount: float) -> tuple[float, float]:
    """(platform fee, host amount). For every payment the platform keeps the commission percentage, the host gets the rest."""
    fee = round(amount * settings.platform_commission_percent / 100, 2)
    return fee, round(amount - fee, 2)
