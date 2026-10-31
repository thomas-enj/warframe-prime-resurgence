from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any

import requests


HISTORY_FILE = Path(__file__).with_name("historique.json")
VAULT_TRADER_URL = "https://api.warframestat.us/pc/vaultTrader"
ITEMS_URL = "https://api.warframestat.us/items"
ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEAPON_CATEGORIES = {
    "Primary",
    "Secondary",
    "Melee",
    "Arch-Gun",
    "Arch-Melee",
}


@dataclass(frozen=True)
class PrimeRotation:
    rotation_key: str
    name: str
    unique_name: str
    activation: datetime
    expiry: datetime


@dataclass(frozen=True)
class PrimeEquipment:
    warframe: str
    weapons: tuple[str, ...]


def load_history() -> set[str]:
    if not HISTORY_FILE.exists():
        return set()

    with HISTORY_FILE.open("r", encoding="utf-8") as history_file:
        history = json.load(history_file)

    if not isinstance(history, list) or any(
        not isinstance(rotation_id, (str, int)) for rotation_id in history
    ):
        raise ValueError(
            "historique.json must contain a JSON list of rotation IDs"
        )

    return {str(rotation_id) for rotation_id in history}


def save_history(history: set[str]) -> None:
    rotation_ids = sorted(history)
    HISTORY_FILE.write_text(
        json.dumps(rotation_ids, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_api_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Missing date in /vaultTrader {label}")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Invalid date in /vaultTrader {label}") from error

    if parsed.tzinfo is None:
        raise ValueError(f"Date has no timezone in /vaultTrader {label}")

    return parsed.astimezone(timezone.utc)


def fetch_schedule() -> tuple[list[dict[str, Any]], datetime]:
    response = requests.get(VAULT_TRADER_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict) or not isinstance(
        payload.get("schedule"), list
    ):
        raise ValueError("Unexpected /vaultTrader response structure")

    initial_start = parse_api_datetime(
        payload.get("initialStart"), "initialStart"
    )
    return payload["schedule"], initial_start


def fetch_items() -> list[dict[str, Any]]:
    response = requests.get(ITEMS_URL, timeout=40)
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, list):
        raise ValueError("Unexpected /items response structure")

    return payload


def extract_rotations(
    schedule: list[dict[str, Any]],
    initial_start: datetime,
) -> list[PrimeRotation]:
    rotations_by_key: dict[str, PrimeRotation] = {}
    schedule_entries = sorted(
        (
            (entry, parse_api_datetime(entry.get("expiry"), "schedule expiry"))
            for entry in schedule
        ),
        key=lambda item: item[1],
    )
    previous_expiry = initial_start.astimezone(timezone.utc)

    for entry, expiry in schedule_entries:
        activation = previous_expiry
        previous_expiry = expiry
        unique_name = entry.get("uniqueName")
        if not isinstance(unique_name, str):
            continue
        if "MegaPrimeVault" not in unique_name:
            continue

        pack_code = unique_name.rsplit("/", 1)[-1]
        if not pack_code.startswith("MPV"):
            continue

        name = entry.get("item")
        if not isinstance(name, str):
            raise ValueError(f"Incomplete schedule entry for {unique_name}")

        rotation_key = expiry.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        rotation = PrimeRotation(
            rotation_key=rotation_key,
            name=name,
            unique_name=unique_name,
            activation=activation,
            expiry=expiry,
        )

        previous = rotations_by_key.get(rotation_key)
        if previous is not None and previous.unique_name != unique_name:
            raise ValueError(
                f"Multiple Prime Resurgence packs share expiry {rotation_key}"
            )
        rotations_by_key[rotation_key] = rotation

    return sorted(rotations_by_key.values(), key=lambda item: item.expiry)


def select_next_rotation(
    rotations: list[PrimeRotation],
    history: set[str],
) -> PrimeRotation | None:
    ordered_rotations = sorted(rotations, key=lambda item: item.expiry)
    if not history:
        return ordered_rotations[0] if ordered_rotations else None

    for index, rotation in enumerate(ordered_rotations):
        if rotation.rotation_key in history:
            continue
        if index == 0:
            return None

        previous_rotation = ordered_rotations[index - 1]
        if previous_rotation.rotation_key in history:
            return rotation
        return None

    return None


def normalize_identifier(value: str) -> str:
    return "".join(
        character.lower() for character in value if character.isalnum()
    )


def extract_rotation_warframes(
    rotation: PrimeRotation,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pack_code = normalize_identifier(rotation.unique_name.rsplit("/", 1)[-1])
    if not pack_code.startswith("mpv"):
        raise ValueError(f"Not a Prime Vault pack: {rotation.unique_name}")

    pack_code = pack_code[3:]
    for suffix in ("singlepack", "dualpack"):
        if pack_code.endswith(suffix):
            pack_code = pack_code[: -len(suffix)]
            break
    if pack_code.endswith("prime"):
        pack_code = pack_code[:-5]

    frames_by_token: dict[str, dict[str, Any]] = {}
    for item in items:
        name = item.get("name")
        if (
            item.get("type") != "Warframe"
            or item.get("isPrime") is not True
            or not isinstance(name, str)
            or not name.endswith(" Prime")
            or not isinstance(item.get("releaseDate"), str)
        ):
            continue

        token = normalize_identifier(name.removesuffix(" Prime"))
        frames_by_token[token] = item

    candidates = sorted(
        frames_by_token.items(),
        key=lambda candidate: len(candidate[0]),
        reverse=True,
    )

    @lru_cache(maxsize=None)
    def parse_pack(remainder: str) -> tuple[tuple[str, ...], ...]:
        if not remainder:
            return ((),)

        matches: list[tuple[str, ...]] = []
        for token, item in candidates:
            if not remainder.startswith(token):
                continue
            for suffix in parse_pack(remainder[len(token):]):
                matches.append((item["name"], *suffix))
                if len(matches) > 1:
                    return tuple(matches)
        return tuple(matches)

    matches = parse_pack(pack_code)
    if len(matches) != 1:
        reason = "could not be parsed" if not matches else "is ambiguous"
        raise ValueError(
            f"Prime pack Warframe list {reason}: {rotation.unique_name}"
        )

    frames_by_name = {item["name"]: item for item in frames_by_token.values()}
    return [frames_by_name[name] for name in matches[0]]


def find_prime_equipment(
    rotation: PrimeRotation,
    items: list[dict[str, Any]],
) -> list[PrimeEquipment]:
    warframes = extract_rotation_warframes(rotation, items)
    weapons_by_release_date: dict[str, set[str]] = {}

    for item in items:
        release_date = item.get("releaseDate")
        name = item.get("name")
        if (
            item.get("isPrime") is True
            and item.get("category") in WEAPON_CATEGORIES
            and isinstance(release_date, str)
            and isinstance(name, str)
        ):
            weapons_by_release_date.setdefault(release_date, set()).add(name)

    return [
        PrimeEquipment(
            warframe=warframe["name"],
            weapons=tuple(
                sorted(
                    weapons_by_release_date.get(
                        warframe["releaseDate"], set()
                    )
                )
            ),
        )
        for warframe in warframes
    ]


def build_discord_payload(
    rotation: PrimeRotation,
    equipment: list[PrimeEquipment],
) -> dict[str, Any]:
    warframe_names = "\n".join(
        f"**{item.warframe}**" for item in equipment
    )
    weapon_list = "\n".join(
        ", ".join(item.weapons) or "No matching Prime weapons"
        for item in equipment
    )
    now = datetime.now(timezone.utc)

    def format_utc_datetime(value: datetime) -> str:
        utc_time = value.astimezone(timezone.utc)
        month = ENGLISH_MONTHS[utc_time.month - 1]
        return (
            f"{utc_time.day} {month} {utc_time.year} at "
            f"{utc_time:%H:%M} UTC"
        )

    def format_english_relative(value: datetime) -> str:
        seconds = int((value - now).total_seconds())
        if seconds == 0:
            return "now"

        future = seconds > 0
        seconds = abs(seconds)
        if seconds < 60:
            amount, unit = seconds, "second"
        elif seconds < 3600:
            amount, unit = round(seconds / 60), "minute"
        elif seconds < 86400:
            amount, unit = round(seconds / 3600), "hour"
        elif seconds < 2_592_000:
            amount, unit = round(seconds / 86400), "day"
        elif seconds < 31_556_952:
            amount, unit = round(seconds / 2_629_746), "month"
        else:
            amount, unit = round(seconds / 31_556_952), "year"

        amount = max(amount, 1)
        label = unit if amount == 1 else f"{unit}s"
        if future:
            return f"in {amount} {label}"
        return f"{amount} {label} ago"

    activation_date = format_utc_datetime(rotation.activation)
    expiry_date = format_utc_datetime(rotation.expiry)
    activation_relative = format_english_relative(rotation.activation)
    expiry_relative = format_english_relative(rotation.expiry)

    return {
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "description": (
                    f"**{rotation.name}** is available in "
                    "the Prime Vault rotation.\n\u200b"
                ),
                "color": 0xD4AF37,
                "fields": [
                    {
                        "name": "🗓️ ROTATION DATES",
                        "value": (
                            f"**Available from** {activation_date} "
                            f"({activation_relative})\n"
                            f"**Until** {expiry_date} "
                            f"({expiry_relative})\n\u200b"
                        ),
                        "inline": False,
                    },
                    {
                        "name": "✨ WARFRAMES",
                        "value": warframe_names,
                        "inline": True,
                    },
                    {
                        "name": "⚔️ PRIME WEAPONS",
                        "value": weapon_list,
                        "inline": True,
                    },
                ],
            }
        ],
    }


def send_discord_webhook(payload: dict[str, Any]) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError(
            "The DISCORD_WEBHOOK_URL environment variable is missing"
        )

    try:
        response = requests.post(webhook_url, json=payload, timeout=20)
    except requests.RequestException as error:
        raise RuntimeError(
            f"Discord webhook request failed ({type(error).__name__})"
        ) from None

    if not response.ok:
        raise RuntimeError(
            f"Discord webhook returned HTTP {response.status_code}"
        )


def main() -> None:
    history = load_history()
    print(f"Loaded {len(history)} published rotation(s).")

    try:
        schedule, initial_start = fetch_schedule()
        rotations = extract_rotations(schedule, initial_start)
        items = fetch_items()
    except (requests.RequestException, ValueError) as error:
        raise SystemExit(
            f"Could not load the Prime Resurgence schedule: {error}"
        )

    if not rotations:
        print("No Prime Resurgence rotations found in /vaultTrader.")
        return

    rotation = select_next_rotation(rotations, history)
    if rotation is None:
        print("No rotation is ready; the previous rotation is not in history.")
        return

    try:
        equipment = find_prime_equipment(rotation, items)
        payload = build_discord_payload(rotation, equipment)
        send_discord_webhook(payload)
    except (requests.RequestException, RuntimeError, ValueError) as error:
        raise SystemExit(
            f"Could not publish the Prime Resurgence alert: {error}"
        )

    history.add(rotation.rotation_key)
    try:
        save_history(history)
    except OSError:
        raise SystemExit(
            "The Discord alert was sent, but "
            "historique.json could not be saved."
        ) from None

    print(f"Published and recorded rotation: {rotation.name}")


if __name__ == "__main__":
    main()
