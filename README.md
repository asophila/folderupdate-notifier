# Folder Monitor and Notifier

A flexible folder monitoring service that watches for changes and sends notifications through various notification services. While originally designed for Syncthing folder synchronization, it can monitor any folder for changes.

## Features

- Monitor multiple folders simultaneously
- Support for various notification services:
  - ntfy
  - Pushover
  - Discord
  - Telegram
  - Gotify
  - Matrix
- Configurable inactivity period before notification
- Custom notification messages
- Persistent configuration
- Detailed logging
- Cross-platform support (Linux, macOS, Windows)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/folder-monitor.git
cd folder-monitor
```

2. Install dependencies:
```bash
pip install watchdog requests
```

## Usage

### Basic Commands

```bash
# Start the monitoring service
python monitor.py start

# Add a folder to monitor (using ntfy)
python monitor.py add downloads ~/Downloads ntfy my-topic

# Remove a monitored folder
python monitor.py remove downloads

# Check status of all monitored folders
python monitor.py status
```

### Notification Services

#### ntfy
```bash
python monitor.py add photos ~/Photos ntfy my-topic \
  --server https://ntfy.sh \
  --message "Photo sync complete in {folder}"
```

#### Pushover
```bash
python monitor.py add docs ~/Documents pushover \
  "app_token" "user_key" \
  --message "Document changes detected in {folder}"
```

#### Discord
```bash
python monitor.py add projects ~/Projects discord \
  "webhook_url" \
  --message "Project files updated in {folder}"
```

#### Telegram
```bash
python monitor.py add downloads ~/Downloads telegram \
  "bot_token" "chat_id" \
  --message "Download complete in {folder}"
```

#### Gotify
```bash
python monitor.py add media ~/Media gotify \
  "https://gotify.example.com" "app_token" \
  --message "Media sync finished in {folder}"
```

#### Matrix
```bash
python monitor.py add backups ~/Backups matrix \
  "https://matrix.org" "access_token" "!room:matrix.org" \
  --message "Backup completed in {folder}"
```

## Inactivity Period Explained

The monitor uses an inactivity period (default: 5 minutes) before sending notifications. This design choice was made for several reasons:

1. **Batch Updates**: When syncing tools like Syncthing update multiple files, you probably want one notification after all changes are complete, not dozens of notifications for each file.

2. **Partial Transfers**: During large file transfers, you want to be notified when the transfer is complete, not when it starts.

3. **Temporary Files**: Many applications create temporary files during operation. The inactivity period helps ignore these transient changes.

4. **Network Efficiency**: For self-hosted notification services, this reduces the number of API calls significantly.

You can adjust this period using the `--inactivity` parameter (specified in seconds):
```bash
python monitor.py add downloads ~/Downloads ntfy my-topic --inactivity 600  # 10 minutes
```

## Running as a Service

### Linux (systemd)

1. Create a systemd service file:
```bash
sudo nano /etc/systemd/system/folder-monitor.service
```

2. Add the following content (adjust paths as needed):
```ini
[Unit]
Description=Folder Monitor Service
After=network.target

[Service]
Type=simple
User=yourusername
ExecStart=/usr/bin/python3 /path/to/monitor.py start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:
```bash
sudo systemctl enable folder-monitor
sudo systemctl start folder-monitor
```

### macOS (launchd)

1. Create a launch agent file:
```bash
nano ~/Library/LaunchAgents/com.user.folder-monitor.plist
```

2. Add the following content (adjust paths):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.folder-monitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/monitor.py</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

3. Load the agent:
```bash
launchctl load ~/Library/LaunchAgents/com.user.folder-monitor.plist
```

### Windows

1. Create a batch file `start-monitor.bat`:
```batch
@echo off
python C:\path\to\monitor.py start
```

2. Create a shortcut to this batch file in the Windows Startup folder:
  - Press `Win + R`
  - Type `shell:startup`
  - Copy the shortcut to the opened folder

Alternatively, use Task Scheduler:
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger to "At system startup"
4. Set action to start the batch file

## Cross-Platform Compatibility

The monitor is built using Python's cross-platform libraries and should work on:

- Linux (all distributions)
- macOS (10.13 or later)
- Windows (7 or later)

Key compatibility notes:

- **Linux**: Full support for all features
- **macOS**: Full support for all features
- **Windows**: 
  - Uses Windows-specific path separators automatically
  - Some file system events might behave slightly differently
  - Service installation process differs (see above)

## Configuration

The monitor stores its configuration in:

- Linux/macOS: `~/.config/syncthing-monitor/config.json`
- Windows: `%APPDATA%\syncthing-monitor\config.json`

Logs are stored in the same directory with the filename `monitor.log`.

## Contributing

Contributions are welcome! Some areas that could use improvement:

- Additional notification services
- Web interface for management
- More detailed status reporting
- Better error handling and recovery
- Cross-platform testing and bug fixes

## License

MIT License - feel free to use, modify, and distribute as needed.
