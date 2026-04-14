# -*- coding: utf-8 -*-
"""Affiche les prix du Bitcoin et de l'Ethereum sur un écran MAX7219.

Améliorations principales :
- Source de prix fiable (API CoinGecko JSON) au lieu d'un parsing HTML fragile.
- Gestion robuste des erreurs réseau + timeout.
- Logging horodaté dans un fichier texte.
- Affichage alterné BTC puis ETH toutes les 3 secondes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import requests
from luma.core.interface.serial import noop, spi
from luma.core.legacy import show_message
from luma.core.legacy.font import LCD_FONT, proportional
from luma.led_matrix.device import max7219


@dataclass(frozen=True)
class Settings:
    """Configuration du script."""

    refresh_seconds: int = 3
    log_file: Path = Path("/home/pi/bitcoin-bar/prix_crypto.txt")
    coingecko_url: str = (
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
    )
    request_timeout: int = 10


def setup_device() -> max7219:
    serial = spi(port=0, device=0, gpio=noop())
    return max7219(serial, cascaded=8, block_orientation=-90, rotate=2)


def setup_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("crypto_display")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        stream_handler = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        file_handler.setFormatter(fmt)
        stream_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger


def fetch_prices_usd(session: requests.Session, settings: Settings) -> dict[str, Optional[Decimal]]:
    """Retourne les prix BTC et ETH en USD."""
    try:
        response = session.get(settings.coingecko_url, timeout=settings.request_timeout)
        response.raise_for_status()
        payload = response.json()

        btc = Decimal(str(payload["bitcoin"]["usd"]))
        eth = Decimal(str(payload["ethereum"]["usd"]))
        return {"BTC": btc, "ETH": eth}
    except (
        requests.RequestException,
        KeyError,
        TypeError,
        InvalidOperation,
        ValueError,
    ):
        return {"BTC": None, "ETH": None}


def format_price(price: Decimal) -> str:
    return f"{price:,.0f}"


def display_message(device: max7219, text: str) -> None:
    show_message(
        device,
        text,
        fill="white",
        font=proportional(LCD_FONT),
        scroll_delay=0.03,
    )


def show_asset(device: max7219, logger: logging.Logger, symbol: str, price: Optional[Decimal]) -> None:
    if price is None:
        logger.warning("Impossible de récupérer le prix %s", symbol)
        display_message(device, f"Erreur {symbol}")
        return

    formatted = format_price(price)
    logger.info("%s: $%s", symbol, formatted)
    display_message(device, f"{symbol}: ${formatted}")


def run() -> None:
    settings = Settings()
    logger = setup_logger(settings.log_file)
    device = setup_device()

    session = requests.Session()
    session.headers.update({"User-Agent": "crypto-max7219-display/1.0"})

    logger.info("Démarrage de l'affichage BTC/ETH sur MAX7219")

    try:
        while True:
            prices = fetch_prices_usd(session, settings)

            show_asset(device, logger, "BTC", prices["BTC"])
            time.sleep(settings.refresh_seconds)

            show_asset(device, logger, "ETH", prices["ETH"])
            time.sleep(settings.refresh_seconds)
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur (Ctrl+C)")
    finally:
        session.close()


if __name__ == "__main__":
    run()
