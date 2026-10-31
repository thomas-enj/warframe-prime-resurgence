import json
from pathlib import Path


HISTORY_FILE = Path(__file__).with_name("historique.json")


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
    rotation_ids = sorted(history, key=int)
    HISTORY_FILE.write_text(
        json.dumps(rotation_ids, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    history = load_history()
    save_history(history)
    print(f"Loaded {len(history)} published rotation(s).")


if __name__ == "__main__":
    main()
