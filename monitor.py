import time
import logging
import json
import argparse
import signal
import sys
from pathlib import Path
from abc import ABC, abstractmethod
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass

CONFIG_PATH = Path.home() / '.config' / 'syncthing-monitor' / 'config.json'
LOG_PATH = Path.home() / '.config' / 'syncthing-monitor' / 'monitor.log'

class NotificationService(ABC):
    @abstractmethod
    def send(self, message: str, title: str = "Sync Complete") -> bool:
        pass

    @staticmethod
    def create(service_type: str, config: dict) -> 'NotificationService':
        services = {
            'ntfy': NtfyService,
            'pushover': PushoverService,
            'discord': DiscordService,
            'telegram': TelegramService,
            'gotify': GotifyService,
            'matrix': MatrixService
        }
        return services[service_type](config)

class NtfyService(NotificationService):
    def __init__(self, config: dict):
        self.server = config.get('server', 'https://ntfy.sh').rstrip('/')
        self.topic = config['topic']

    def send(self, message: str, title: str = "Sync Complete") -> bool:
        try:
            response = requests.post(
                f"{self.server}/{self.topic}",
                data=message.encode('utf-8'),
                headers={
                    "Title": title,
                    "Priority": "default",
                    "Tags": "sync,complete"
                }
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send ntfy notification: {e}")
            return False

class PushoverService(NotificationService):
    def __init__(self, config: dict):
        self.api_token = config['api_token']
        self.user_key = config['user_key']

    def send(self, message: str, title: str = "Sync Complete") -> bool:
        try:
            response = requests.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": self.api_token,
                    "user": self.user_key,
                    "message": message,
                    "title": title
                }
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send Pushover notification: {e}")
            return False

class DiscordService(NotificationService):
    def __init__(self, config: dict):
        self.webhook_url = config['webhook_url']

    def send(self, message: str, title: str = "Sync Complete") -> bool:
        try:
            response = requests.post(
                self.webhook_url,
                json={
                    "content": message,
                    "embeds": [{
                        "title": title,
                        "color": 5814783
                    }]
                }
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send Discord notification: {e}")
            return False

class TelegramService(NotificationService):
    def __init__(self, config: dict):
        self.bot_token = config['bot_token']
        self.chat_id = config['chat_id']

    def send(self, message: str, title: str = "Sync Complete") -> bool:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": f"*{title}*\n{message}",
                    "parse_mode": "Markdown"
                }
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send Telegram notification: {e}")
            return False

class GotifyService(NotificationService):
    def __init__(self, config: dict):
        self.server = config['server'].rstrip('/')
        self.token = config['token']

    def send(self, message: str, title: str = "Sync Complete") -> bool:
        try:
            response = requests.post(
                f"{self.server}/message",
                headers={"X-Gotify-Key": self.token},
                json={
                    "message": message,
                    "title": title,
                    "priority": 5
                }
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send Gotify notification: {e}")
            return False

class MatrixService(NotificationService):
    def __init__(self, config: dict):
        self.homeserver = config['homeserver'].rstrip('/')
        self.access_token = config['access_token']
        self.room_id = config['room_id']

    def send(self, message: str, title: str = "Sync Complete") -> bool:
        try:
            response = requests.post(
                f"{self.homeserver}/_matrix/client/r0/rooms/{self.room_id}/send/m.room.message",
                params={"access_token": self.access_token},
                json={
                    "msgtype": "m.text",
                    "body": f"{title}\n{message}",
                    "format": "org.matrix.custom.html",
                    "formatted_body": f"<strong>{title}</strong><br>{message}"
                }
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send Matrix notification: {e}")
            return False

class SyncthingHandler(FileSystemEventHandler):
    def __init__(self, folder_name: str, callback, inactivity_period: int = 300):
        self.folder_name = folder_name
        self.callback = callback
        self.last_modified = datetime.now()
        self.inactivity_period = inactivity_period
        self.timer_running = False
        self.active = True

    def on_any_event(self, event):
        if not self.active or event.is_directory or event.src_path.split('/')[-1].startswith('.'):
            return
        
        self.last_modified = datetime.now()
        logging.info(f"[{self.folder_name}] Change detected: {event.src_path}")
        
        if not self.timer_running:
            self.timer_running = True
            self.start_inactivity_timer()

    def start_inactivity_timer(self):
        while self.active:
            time_since_last_mod = (datetime.now() - self.last_modified).total_seconds()
            
            if time_since_last_mod >= self.inactivity_period:
                logging.info(f"[{self.folder_name}] No changes detected for {self.inactivity_period}s")
                self.callback(self.folder_name)
                self.timer_running = False
                break
                
            time.sleep(10)

    def stop(self):
        self.active = False

class MonitorService:
    def __init__(self):
        self.config = self._load_config()
        self.observers: Dict[str, Observer] = {}
        self.handlers: Dict[str, SyncthingHandler] = {}
        self.notification_services: Dict[str, NotificationService] = {}
        self._setup_logging()

    def _setup_logging(self):
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_PATH),
                logging.StreamHandler()
            ]
        )

    def _load_config(self) -> dict:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                return json.load(f)
        return {"folders": {}}

    def _save_config(self):
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)

    def send_ntfy_notification(self, folder_name: str):
        folder_config = self.config["folders"][folder_name]
        try:
            ntfy_server = folder_config.get('ntfy_server', 'https://ntfy.sh').rstrip('/')
            message = folder_config.get('message', 'Sync complete for {folder}').format(folder=folder_name)
            
            response = requests.post(
                f"{ntfy_server}/{folder_config['ntfy_topic']}",
                data=message.encode('utf-8'),
                headers={
                    "Title": "Sync Complete",
                    "Priority": "default",
                    "Tags": "sync,complete"
                }
            )
            response.raise_for_status()
            logging.info(f"[{folder_name}] Notification sent successfully")
        except requests.exceptions.RequestException as e:
            logging.error(f"[{folder_name}] Failed to send notification: {e}")

    def remove_folder(self, name: str) -> bool:
        if name not in self.observers:
            logging.error(f"Folder '{name}' not found")
            return False

        self.handlers[name].stop()
        self.observers[name].stop()
        self.observers[name].join()

        del self.observers[name]
        del self.handlers[name]
        del self.config["folders"][name]
        self._save_config()

        logging.info(f"Stopped monitoring '{name}'")
        return True

    def get_status(self) -> dict:
        status = {}
        for name, handler in self.handlers.items():
            status[name] = {
                "path": self.config["folders"][name]["path"],
                "ntfy_topic": self.config["folders"][name]["ntfy_topic"],
                "inactivity_period": self.config["folders"][name]["inactivity_period"],
                "last_modified": handler.last_modified.isoformat(),
                "timer_running": handler.timer_running
            }
        return status

    def start(self):
        for name, folder in self.config["folders"].items():
            self.add_folder(
                name,
                folder["path"],
                folder["ntfy_topic"],
                folder["inactivity_period"]
            )

    def stop(self):
        for name in list(self.observers.keys()):
            self.remove_folder(name)

    def add_folder(self, name: str, path: str, notification_config: dict, inactivity_period: int = 300) -> bool:
        if name in self.observers:
            logging.error(f"Folder '{name}' already being monitored")
            return False

        if not Path(path).exists():
            logging.error(f"Path '{path}' does not exist")
            return False

        try:
            service = NotificationService.create(
                notification_config['type'],
                notification_config['config']
            )
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid notification configuration: {e}")
            return False

        self.config["folders"][name] = {
            "path": path,
            "notification": notification_config,
            "inactivity_period": inactivity_period,
            "message_template": notification_config.get('message', "Sync complete for {folder}")
        }
        self._save_config()

        self.notification_services[name] = service
        
        handler = SyncthingHandler(
            name,
            self.send_notification,
            inactivity_period
        )
        observer = Observer()
        observer.schedule(handler, path, recursive=True)
        observer.start()

        self.observers[name] = observer
        self.handlers[name] = handler
        
        logging.info(f"Started monitoring '{name}' at '{path}'")
        return True

    def send_notification(self, folder_name: str):
        if folder_name not in self.notification_services:
            logging.error(f"No notification service found for {folder_name}")
            return

        folder_config = self.config["folders"][folder_name]
        message = folder_config["message_template"].format(folder=folder_name)
        service = self.notification_services[folder_name]
        
        if service.send(message):
            logging.info(f"[{folder_name}] Notification sent successfully")
        else:
            logging.error(f"[{folder_name}] Failed to send notification")

def main():
    parser = argparse.ArgumentParser(
        description="Syncthing folder monitor service with multiple notification options"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Start service command
    subparsers.add_parser("start", help="Start the monitor service")

    # Add folder command
    add_parser = subparsers.add_parser(
        "add",
        help="Add a folder to monitor",
        description="Add a new folder to be monitored for Syncthing updates"
    )
    add_parser.add_argument("name", help="Name for the monitored folder")
    add_parser.add_argument("path", help="Path to the folder")
    
    # Notification service subparsers
    notification_subparsers = add_parser.add_subparsers(
        dest="notification_type",
        help="Notification service to use",
        required=True
    )

    # ntfy configuration
    ntfy_parser = notification_subparsers.add_parser("ntfy", help="Use ntfy for notifications")
    ntfy_parser.add_argument("topic", help="ntfy topic")
    ntfy_parser.add_argument("--server", default="https://ntfy.sh",
                            help="ntfy server URL (default: https://ntfy.sh)")

    # Pushover configuration
    pushover_parser = notification_subparsers.add_parser("pushover", help="Use Pushover for notifications")
    pushover_parser.add_argument("api_token", help="Pushover API token")
    pushover_parser.add_argument("user_key", help="Pushover user key")

    # Discord configuration
    discord_parser = notification_subparsers.add_parser("discord", help="Use Discord for notifications")
    discord_parser.add_argument("webhook_url", help="Discord webhook URL")

    # Telegram configuration
    telegram_parser = notification_subparsers.add_parser("telegram", help="Use Telegram for notifications")
    telegram_parser.add_argument("bot_token", help="Telegram bot token")
    telegram_parser.add_argument("chat_id", help="Telegram chat ID")

    # Gotify configuration
    gotify_parser = notification_subparsers.add_parser("gotify", help="Use Gotify for notifications")
    gotify_parser.add_argument("server", help="Gotify server URL")
    gotify_parser.add_argument("token", help="Gotify application token")

    # Matrix configuration
    matrix_parser = notification_subparsers.add_parser("matrix", help="Use Matrix for notifications")
    matrix_parser.add_argument("homeserver", help="Matrix homeserver URL")
    matrix_parser.add_argument("access_token", help="Matrix access token")
    matrix_parser.add_argument("room_id", help="Matrix room ID")

    # Common options for all notification services
    for p in notification_subparsers.choices.values():
        p.add_argument("--message", help='Custom notification message. Use {folder} as placeholder')
        p.add_argument("--inactivity", type=int, default=300,
                      help="Inactivity period in seconds before sending notification (default: 300)")

    # Remove folder command
    remove_parser = subparsers.add_parser("remove", help="Remove a monitored folder")
    remove_parser.add_argument("name", help="Name of the monitored folder")

    # Status command
    subparsers.add_parser("status", help="Show status of monitored folders")

    args = parser.parse_args()
    service = MonitorService()

    if args.command == "start":
        def signal_handler(signum, frame):
            logging.info("Stopping service...")
            service.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        service.start()
        logging.info("Service started. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)

    elif args.command == "add":
        # Convert args to notification config
        notification_config = {
            "type": args.notification_type,
            "config": vars(args),
            "message": args.message
        }
        service.add_folder(args.name, args.path, notification_config, args.inactivity)

    elif args.command == "remove":
        service.remove_folder(args.name)

    elif args.command == "status":
        status = service.get_status()
        print(json.dumps(status, indent=2))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
