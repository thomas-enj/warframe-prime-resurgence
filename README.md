# Warframe Prime Resurgence Bot

This bot monitors Warframe Prime Resurgence rotations and posts a Discord notification when a new rotation is available. It retrieves the schedule and item data from the public [Warframe Status API](https://api.warframestat.us/).

Notifications include the rotation dates in Paris time, the Prime Warframes in the rotation, and their associated Prime weapons.

## How It Works

Each run:

1. Retrieves the Prime Vault schedule and Warframe item data.
2. Identifies the next Prime Resurgence rotation to publish.
3. Sends a Discord embed through a webhook.
4. Records the rotation key in `historique.json` to avoid duplicate notifications.

The GitHub Actions workflow runs the bot every 12 hours and commits the updated history to the repository so it is preserved between runs.

## Requirements

- Python 3.9 or later
- A Discord webhook for the channel where notifications should be posted

## Local Setup and Usage

From the repository root, create a virtual environment:

```bash
python -m venv .venv
```

Activate it and install the dependencies:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
python -m pip install -r requirements.txt
```

Set the Discord webhook URL:

```bash
# Linux/macOS
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

```powershell
# Windows PowerShell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
```

Run the bot:

```bash
python prime_resurgence_bot.py
```

A local run can send a notification and update `historique.json`, just like an automated run.

## GitHub Actions Configuration

To enable automated runs:

1. In the repository settings, add `DISCORD_WEBHOOK_URL` as a secret under **Settings > Secrets and variables > Actions**.
2. Make sure GitHub Actions is enabled for the repository.

The [check_resurgence.yml](.github/workflows/check_resurgence.yml) workflow runs every 12 hours and can also be started manually from the **Actions** tab. It uses Python 3.13 and the `contents: write` permission to commit changes to `historique.json`.

## Key Files

- [prime_resurgence_bot.py](prime_resurgence_bot.py): fetches data, detects rotations, and posts Discord notifications.
- [historique.json](historique.json): stores the keys of rotations that have already been published.
- [requirements.txt](requirements.txt): Python dependencies.
- [.github/workflows/check_resurgence.yml](.github/workflows/check_resurgence.yml): scheduled GitHub Actions workflow.
- [.github/dependabot.yml](.github/dependabot.yml): weekly updates for Python dependencies and GitHub Actions.