# Running the bot 24/7

These steps are for a Debian or Ubuntu server (or Raspberry Pi OS) with Python 3.10+. The bot uses polling, so it needs no domain, web server or open web port. You only need SSH access.

**Run only one copy.** Stop the bot on your computer before starting it on the server.

## 1. Install (on the server)

```bash
sudo apt update && sudo apt install -y git python3-venv
sudo useradd --system --home-dir /opt/expense-tracker --shell /usr/sbin/nologin expense
sudo git clone https://github.com/sagar-shelke/personal-expense-tracker.git /opt/expense-tracker
sudo chown -R expense:expense /opt/expense-tracker
cd /opt/expense-tracker
sudo -u expense python3 -m venv .venv
sudo -u expense .venv/bin/pip install --no-cache-dir -r requirements.txt
```

## 2. Add your secrets

Copy your `.env` and Google JSON key to the server over SSH (for example with `scp`, or your provider's upload button). Never commit or share them. If you uploaded them to your home folder:

```bash
sudo install -d -o expense -g expense -m 700 /opt/expense-tracker/credentials
sudo install -o expense -g expense -m 600 ~/.env /opt/expense-tracker/.env
sudo install -o expense -g expense -m 600 ~/service-account.json /opt/expense-tracker/credentials/service-account.json
rm ~/.env ~/service-account.json
```

In `/opt/expense-tracker/.env`, set:

```
GOOGLE_APPLICATION_CREDENTIALS=credentials/service-account.json
```

If you are moving an existing bot, first send `/status` and make sure no saves are unfinished and no transaction awaits YES or NO. The server then starts with a new local database. Your saved rows stay in Google Sheets.

## 3. Start the service

```bash
sudo cp /opt/expense-tracker/deploy/expense-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now expense-tracker
sudo systemctl status expense-tracker
```

It now starts at boot and restarts if it crashes.

## 4. Check it

1. Send `/status` in Telegram.
2. Save a small test entry, check the sheet, then delete the row.
3. Run `sudo reboot`, wait a few minutes, and send `/status` again.

## Everyday tasks

| Task | Command |
|---|---|
| Live logs | `sudo journalctl -u expense-tracker -f` |
| Restart | `sudo systemctl restart expense-tracker` |
| Stop | `sudo systemctl stop expense-tracker` |

**Update the app:**

```bash
cd /opt/expense-tracker
sudo systemctl stop expense-tracker
sudo -u expense git pull --ff-only
sudo -u expense .venv/bin/pip install --no-cache-dir -r requirements.txt
sudo systemctl start expense-tracker
```

If the service file changed, repeat step 3 and restart.

## Upkeep

- The bot does not alert you if the server goes offline. If it stops replying, check the server and logs.
- Install system security updates regularly: `sudo apt update && sudo apt upgrade`.
- Google Sheets holds your saved records. Download a copy now and then.
- `expense_tracker.db` holds pending and unfinished saves, so don't delete it.
- The table holds 500 transactions. Before it fills, add rows and increase `TABLE_END_ROW` in `app/sheets.py` (through GitHub, then update).
- If your bot token or Google key is exposed, revoke it and create a new one.
