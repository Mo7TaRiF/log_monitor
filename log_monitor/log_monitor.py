#!/usr/bin/env python3
import os
import time
from datetime import datetime
import pytz
import subprocess
import threading
import signal
import sys

# تكوينات البرنامج
LOG_FILES = [
    {
        'path': '/root/tf2autobot/logs/mo7tarif313.error.log',
        'pm2_name': 'Tiny Trading'  # اسم التطبيق في PM2
    },
    {
        'path': '/root/tf2autobot/logs/mo7tarif701.error.log',
        'pm2_name': 'Kits and Items'  # اسم التطبيق في PM2
    }
]
ERROR_PATTERN = '"level":"error","message":"Error on update listings:,"'
TIMEZONE = pytz.timezone('Europe/London')
LOG_FILE = '/var/log/log_monitor.log'  # ملف سجل خاص ببرنامج المراقبة


class LogMonitor:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        # إنشاء ملف السجل إذا لم يكن موجودًا
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    def handle_signal(self, signum, frame):
        self.log_message(f"تم استقبال إشارة إيقاف ({signum})، إيقاف المراقبة...")
        self.running = False

    def log_message(self, message):
        """تسجيل الرسائل في ملف السجل"""
        timestamp = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        with open(LOG_FILE, 'a') as f:
            f.write(log_entry)

        print(log_entry.strip())

    def monitor_log_file(self, log_config):
        """تراقب ملف السجل وتتحقق من وجود نمط الخطأ"""
        file_path = log_config['path']
        pm2_name = log_config['pm2_name']

        self.log_message(f"بدء مراقبة ملف السجل: {file_path} للتطبيق {pm2_name}")

        try:
            file_size = os.path.getsize(file_path)
        except FileNotFoundError:
            self.log_message(f"ملف السجل غير موجود: {file_path}")
            return

        while self.running:
            try:
                current_size = os.path.getsize(file_path)

                if current_size > file_size:
                    with open(file_path, 'r') as file:
                        file.seek(file_size)
                        new_content = file.read()

                        if ERROR_PATTERN in new_content:
                            self.log_message(f"تم اكتشاف خطأ في {pm2_name}، إيقاف التطبيق...")

                            try:
                                result = subprocess.run(
                                    ["pm2", "stop", pm2_name],
                                    capture_output=True,
                                    text=True,
                                    check=True
                                )
                                self.log_message(f"تم إيقاف {pm2_name} بنجاح")
                                self.log_message(f"الإخراج: {result.stdout}")
                            except subprocess.CalledProcessError as e:
                                self.log_message(f"خطأ في إيقاف {pm2_name}: {e.stderr}")
                            except Exception as e:
                                self.log_message(f"خطأ غير متوقع: {str(e)}")

                    file_size = current_size

                time.sleep(1)

            except FileNotFoundError:
                self.log_message(f"ملف السجل غير موجود مؤقتًا: {file_path}")
                time.sleep(5)
            except Exception as e:
                self.log_message(f"خطأ غير متوقع في مراقبة {pm2_name}: {str(e)}")
                time.sleep(5)

    def run(self):
        """بدء مراقبة جميع ملفات السجل"""
        self.log_message("بدء مراقبة ملفات السجل...")

        threads = []
        for log_config in LOG_FILES:
            thread = threading.Thread(target=self.monitor_log_file, args=(log_config,))
            thread.daemon = True
            thread.start()
            threads.append(thread)

        # الانتظار حتى يتم إيقاف جميع الخيوط
        while self.running:
            time.sleep(1)

        for thread in threads:
            thread.join()

        self.log_message("تم إيقاف مراقبة ملفات السجل")


if __name__ == "__main__":
    monitor = LogMonitor()
    monitor.run()