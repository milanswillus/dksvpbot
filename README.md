# Student Classes Telegram Bot

A simple Telegram Bot for students to manage their class subscriptions.

## Features
- `/add <class>`: Subscribe to a class.
- `/remove <class>`: Unsubscribe from a class.
- `/classes`: View your subscriptions.
- `/start`: Welcome message.

## Setup

1.  **Set up Virtual Environment (Recommended)**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    - Rename `.env` (or create one) and add your bot token:
      ```
      TELEGRAM_BOT_TOKEN=your_token_here
      ```
    - **Note**: You must get this token from @BotFather on Telegram.

3.  **Run**:
    ```bash
    python main.py
    ```

## Running on Raspberry Pi

### Option 1: Systemd (Recommended)
1.  Copy `bot.service` to `/etc/systemd/system/`.
2.  Edit the file to match your user (`User=pi`) and paths.
3.  Enable and start:
    ```bash
    sudo systemctl enable bot
    sudo systemctl start bot
    ```

### Option 2: Docker
1.  Build: `docker build -t student-bot .`
2.  Run: `docker run -d --env-file .env -v $(pwd)/data.json:/app/data.json --name my-bot student-bot`
