#!/usr/bin/env python3
import os
import time
import json
import threading
import signal
import subprocess
from datetime import datetime
import pytz

# تكوينات السيرفر
LOG_FILES = [
    {
        'path': '/root/tf2autobot/logs/mo7tarif313.error.log',
        'pm2_name': 'Tiny Trading',
        'display_name': 'Tiny Trading'
    },
    {
        'path': '/root/tf2autobot/logs/mo7tarif701.error.log',
        'pm2_name': 'Kits and Items',
        'display_name': 'Kits and Items'
    }
]
TIMEZONE = pytz.timezone('Europe/London')
ERROR_PATTERN = {
    "level": "error",
    "message": "Error on update listings:"
}


class LogMonitor:
    def __init__(self):
        self.running = True
        self.lock = threading.Lock()
        self.stopped_apps = []
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

    def handle_signal(self, signum, frame):
        """معالجة إشارات الإيقاف"""
        with self.lock:
            self.running = False
            print(
                f"\nتم استقبال إشارة الإيقاف، التطبيقات الموقفة: {', '.join(self.stopped_apps) if self.stopped_apps else 'لا يوجد'}")

    def log_message(self, message):
        """تسجيل الرسائل في stdout لالتقاطها بواسطة PM2"""
        timestamp = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)

    def check_error(self, line):
        """التحقق من وجود الخطأ المحدد"""
        try:
            log_data = json.loads(line.strip())
            return all(log_data.get(k) == v for k, v in ERROR_PATTERN.items())
        except json.JSONDecodeError:
            return False

    def stop_pm2_app(self, pm2_name, display_name):
        try:
            subprocess.run(['pm2', 'stop', pm2_name], check=True)
            self.log_message(f"تم إيقاف {display_name}")

            # إعادة التشغيل بعد 5 دقائق (300 ثانية)
            time.sleep(300)
            subprocess.run(['pm2', 'start', pm2_name], check=True)
            self.log_message(f"تم إعادة تشغيل {display_name}")

            return True
        except subprocess.CalledProcessError as e:
            self.log_message(f"خطأ: {e.stderr}")
            return False

    def monitor_file(self, log_config):
        """مراقبة ملف سجل واحد"""
        file_path = log_config['path']
        pm2_name = log_config['pm2_name']
        display_name = log_config['display_name']

        self.log_message(f"بدء مراقبة {display_name} ({file_path})")

        try:
            file_position = os.path.getsize(file_path)
        except FileNotFoundError:
            self.log_message(f"الملف غير موجود: {file_path}")
            return

        while self.running:
            try:
                current_size = os.path.getsize(file_path)

                if current_size > file_position:
                    with open(file_path, 'r') as f:
                        f.seek(file_position)
                        new_lines = f.readlines()
                        file_position = f.tell()

                        for line in new_lines:
                            if self.check_error(line):
                                self.log_message(f"تم اكتشاف خطأ في {display_name}")
                                if self.stop_pm2_app(pm2_name, display_name):
                                    with self.lock:
                                        self.stopped_apps.append(f"{display_name} ({pm2_name})")
                                break

                time.sleep(1)

            except FileNotFoundError:
                self.log_message(f"الملف غير موجود مؤقتًا: {file_path}")
                time.sleep(5)
            except Exception as e:
                self.log_message(f"خطأ غير متوقع في {display_name}: {str(e)}")
                time.sleep(5)

    def start(self):
        """بدء المراقبة المتزامنة"""
        threads = []
        for config in LOG_FILES:
            thread = threading.Thread(target=self.monitor_file, args=(config,))
            thread.daemon = True
            thread.start()
            threads.append(thread)

        # الانتظار حتى انتهاء جميع الخيوط
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    monitor = LogMonitor()
    monitor.log_message("=== بدء نظام مراقبة السجلات ===")
    monitor.start()
    monitor.log_message("=== انتهاء نظام مراقبة السجلات ===")