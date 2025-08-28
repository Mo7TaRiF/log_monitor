#!/usr/bin/env python3
import os
import time
import json
import threading
import signal
import subprocess
from datetime import datetime, timedelta
import pytz

# تكوينات السيرفر
LOG_FILES = [
    # الملفات الأصلية
    {
        'path': '/root/tf2autobot/logs/mo7tarif313.error.log',
        'pm2_name': 'Tiny Trading',
        'display_name': 'Tiny Trading',
        'restart_after_stop': True,
        'restart_on_inactivity': False
    },
    {
        'path': '/root/tf2autobot/logs/mo7tarif701.error.log',
        'pm2_name': 'Kits and Items',
        'display_name': 'Kits and Items',
        'restart_after_stop': True,
        'restart_on_inactivity': False
    },
    # الملفات الجديدة للمراقبة
    {
        'path': '/root/.pm2/logs/tiny-pricer-error.log',
        'pm2_name': 'tiny-pricer',
        'display_name': 'Tiny Pricer',
        'restart_after_stop': False,
        'restart_on_inactivity': True
    },
    {
        'path': '/root/.pm2/logs/kits-pricer-error.log',
        'pm2_name': 'kits-pricer',
        'display_name': 'Kits Pricer',
        'restart_after_stop': False,
        'restart_on_inactivity': True
    }
]
TIMEZONE = pytz.timezone('Europe/London')
ERROR_PATTERN = {
    "level": "error",
    "message": "Error on update listings:"
}
INACTIVITY_TIMEOUT = 300  # 5 دقائق بالثواني
RESTART_AFTER_STOP = 300  # 5 دقائق بعد الإيقاف


class LogMonitor:
    def __init__(self):
        self.running = True
        self.lock = threading.Lock()
        self.stopped_apps = []
        self.apps_to_restart = {}  # {pm2_name: restart_time}
        self.last_activity = {}  # لتتبع آخر نشاط لكل ملف
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        # تهيئة وقت آخر نشاط
        for log in LOG_FILES:
            self.last_activity[log['path']] = datetime.now(TIMEZONE)

    def handle_signal(self, signum, frame):
        """معالجة إشارات الإيقاف"""
        with self.lock:
            self.running = False
            signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
            print(f"\nتم استقبال إشارة {signal_name}")
            if self.stopped_apps:
                print(f"التطبيقات الموقفة: {', '.join(self.stopped_apps)}")
            if self.apps_to_restart:
                print(f"التطبيقات المجدولة للإعادة التشغيل: {', '.join(self.apps_to_restart.keys())}")

    def log_message(self, message):
        """تسجيل الرسائل"""
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

    def manage_pm2_app(self, pm2_name, display_name, action='stop'):
        """إدارة تطبيقات PM2 (إيقاف/تشغيل/إعادة تشغيل)"""
        try:
            result = subprocess.run(
                ['pm2', action, pm2_name],
                capture_output=True,
                text=True,
                check=True
            )
            status = "إيقاف" if action == 'stop' else "تشغيل" if action == 'start' else "إعادة تشغيل"
            self.log_message(f"تم {status} {display_name} ({pm2_name}) بنجاح")
            return True
        except subprocess.CalledProcessError as e:
            status = "إيقاف" if action == 'stop' else "تشغيل" if action == 'start' else "إعادة تشغيل"
            self.log_message(f"فشل {status} {display_name} ({pm2_name}): {e.stderr.strip()}")
            return False

    def schedule_restart(self, pm2_name, display_name):
        """جدولة إعادة التشغيل بعد 5 دقائق"""
        restart_time = datetime.now(TIMEZONE) + timedelta(seconds=RESTART_AFTER_STOP)
        with self.lock:
            self.apps_to_restart[pm2_name] = {
                'display_name': display_name,
                'restart_time': restart_time,
                'scheduled_time': datetime.now(TIMEZONE)
            }
        self.log_message(f"تم جدولة إعادة تشغيل {display_name} بعد 5 دقائق")

    def check_scheduled_restarts(self):
        """التحقق من التطبيقات المجدولة للإعادة التشغيل"""
        while self.running:
            try:
                current_time = datetime.now(TIMEZONE)
                apps_to_remove = []

                with self.lock:
                    for pm2_name, app_info in self.apps_to_restart.items():
                        if current_time >= app_info['restart_time']:
                            self.log_message(f"إعادة تشغيل {app_info['display_name']} كما تم جدولته...")
                            if self.manage_pm2_app(pm2_name, app_info['display_name'], 'restart'):
                                apps_to_remove.append(pm2_name)
                            else:
                                # إعادة الجدولة إذا فشلت المحاولة
                                app_info['restart_time'] = current_time + timedelta(seconds=60)

                # إزالة التطبيقات التي تمت إعادة تشغيلها بنجاح
                for pm2_name in apps_to_remove:
                    self.apps_to_restart.pop(pm2_name, None)

                time.sleep(10)  # التحقق كل 10 ثواني

            except Exception as e:
                self.log_message(f"خطأ في التحقق من الجداول: {str(e)}")
                time.sleep(30)

    def check_inactivity_and_restart(self):
        """التحقق من عدم النشاط وإعادة التشغيل إذا لزم الأمر"""
        while self.running:
            try:
                current_time = datetime.now(TIMEZONE)

                for log in LOG_FILES:
                    if log.get('restart_on_inactivity'):
                        last_activity_time = self.last_activity[log['path']]
                        inactivity_duration = (current_time - last_activity_time).total_seconds()

                        if inactivity_duration >= INACTIVITY_TIMEOUT:
                            self.log_message(
                                f"لم يتم اكتشاف نشاط في {log['display_name']} لمدة {inactivity_duration:.0f} ثانية، إعادة التشغيل...")
                            if self.manage_pm2_app(log['pm2_name'], log['display_name'], 'restart'):
                                self.last_activity[log['path']] = current_time  # إعادة ضبط المؤقت

                time.sleep(30)  # التحقق كل 30 ثانية

            except Exception as e:
                self.log_message(f"خطأ في التحقق من النشاط: {str(e)}")
                time.sleep(60)

    def monitor_file(self, log_config):
        """مراقبة ملف سجل واحد"""
        file_path = log_config['path']
        pm2_name = log_config['pm2_name']
        display_name = log_config['display_name']
        restart_after_stop = log_config.get('restart_after_stop', False)

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

                        # تحديث وقت آخر نشاط
                        self.last_activity[file_path] = datetime.now(TIMEZONE)

                        for line in new_lines:
                            if self.check_error(line):
                                self.log_message(f"تم اكتشاف خطأ في {display_name}")
                                if self.manage_pm2_app(pm2_name, display_name, 'stop'):
                                    with self.lock:
                                        self.stopped_apps.append(f"{display_name} ({pm2_name})")

                                    # جدولة إعادة التشغيل إذا كان مفعلًا
                                    if restart_after_stop:
                                        self.schedule_restart(pm2_name, display_name)
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

        # بدء مراقبة جميع الملفات
        for config in LOG_FILES:
            thread = threading.Thread(target=self.monitor_file, args=(config,))
            thread.daemon = True
            thread.start()
            threads.append(thread)

        # بدء مراقبة عدم النشاط
        inactivity_thread = threading.Thread(target=self.check_inactivity_and_restart)
        inactivity_thread.daemon = True
        inactivity_thread.start()
        threads.append(inactivity_thread)

        # بدء مراقبة الجداول الزمنية للإعادة التشغيل
        restart_thread = threading.Thread(target=self.check_scheduled_restarts)
        restart_thread.daemon = True
        restart_thread.start()
        threads.append(restart_thread)

        # الانتظار حتى انتهاء جميع الخيوط
        for thread in threads:
            thread.join()


if __name__ == "__main__":
    monitor = LogMonitor()
    monitor.log_message("=== بدء نظام مراقبة السجلات مع إعادة التشغيل التلقائي ===")
    monitor.log_message("سيتم إعادة تشغيل التطبيقات الرئيسية بعد 5 دقائق من الإيقاف")
    monitor.start()
    monitor.log_message("=== انتهاء نظام مراقبة السجلات ===")