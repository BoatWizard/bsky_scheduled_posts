import sys
import datetime
import threading
import time
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QMainWindow, QSystemTrayIcon, QMenu, QVBoxLayout, QWidget, 
    QTextEdit, QSpinBox, QDateEdit, QPushButton, QLabel, QHBoxLayout, QListWidget, QMessageBox, QListWidgetItem)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QDate, Qt
from atproto import Client

scheduled_posts = []

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")

        self.username_label = QLabel("Username:")
        self.username_input = QLineEdit()

        self.password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)

        self.setLayout(layout)

    def get_credentials(self):
        return self.username_input.text(), self.password_input.text()


class TrayApp(QMainWindow):
    def __init__(self, client):
        super().__init__()
        self.client = client

        # Tray icon setup
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("icon.png"))
        self.tray_icon.setToolTip("BlueSky Scheduler")
        self.tray_icon.activated.connect(self.show_window)

        tray_menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_window)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Main window setup
        self.setWindowTitle("BlueSky Scheduler")
        self.setGeometry(100, 100, 400, 400)

        layout = QVBoxLayout()
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        layout.addWidget(QLabel("Enter your Skeet:"))

        self.text_box = QTextEdit(self)
        layout.addWidget(self.text_box)

        layout.addWidget(QLabel("Post Date:"))
        self.date_picker = QDateEdit(self)
        self.date_picker.setDate(QDate.currentDate())
        layout.addWidget(self.date_picker)

        time_layout = QHBoxLayout()
        layout.addLayout(time_layout)

        time_layout.addWidget(QLabel("Post Time (24h):"))
        self.hour_spin = QSpinBox(self)
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setValue(12)
        time_layout.addWidget(self.hour_spin)

        time_layout.addWidget(QLabel(":"))
        self.minute_spin = QSpinBox(self)
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setValue(0)
        time_layout.addWidget(self.minute_spin)

        schedule_button = QPushButton("Schedule Post", self)
        schedule_button.clicked.connect(self.schedule_post)
        layout.addWidget(schedule_button)

        self.queue_list = QListWidget(self)
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.queue_list)

    def show_window(self):
        self.show()

    def hide_window(self):
        self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def quit_app(self):
        self.tray_icon.hide()
        QApplication.quit()

    def update_queue_display(self, entry, post_time, content):
        item = QListWidgetItem(entry)
        item.setData(32, (post_time, content))
        self.queue_list.addItem(item)
        self.queue_list.scrollToBottom()

    def schedule_post(self):
        content = self.text_box.toPlainText().strip()
        hour = self.hour_spin.value()
        minute = self.minute_spin.value()
        selected_date = self.date_picker.date().toPyDate()
        post_time = datetime.datetime.combine(selected_date, datetime.time(hour, minute))

        if not content:
            print("Warning: Your post is empty!")
            return

        if post_time < datetime.datetime.now():
            confirm = QMessageBox.question(
                self,
                "Post time is in the past",
                "The scheduled time is in the past. Post immediately?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                post = self.client.send_post(content)
                print("Posted:", post.uri)
                self.update_queue_display(f"✅ {post_time.strftime('%Y-%m-%d %H:%M')} — Posted", post_time, content)
            except Exception as e:
                self.update_queue_display(f"❌ {post_time.strftime('%Y-%m-%d %H:%M')} — Error: {e}", post_time, content)
            return

        def post_later():
            delay = (post_time - datetime.datetime.now()).total_seconds()
            time.sleep(max(0, delay))
            try:
                post = self.client.send_post(content)
                print("Posted:", post.uri)
                self.update_queue_display(f"✅ {post_time.strftime('%Y-%m-%d %H:%M')} — Posted", post_time, content)
            except Exception as e:
                self.update_queue_display(f"❌ {post_time.strftime('%Y-%m-%d %H:%M')} — Error: {e}", post_time, content)

        t = threading.Thread(target=post_later, daemon=True)
        t.start()

        self.update_queue_display(f"🕒 {post_time.strftime('%Y-%m-%d %H:%M')} — Queued", post_time, content)
        scheduled_posts.append((post_time, content))

        self.text_box.clear()
        self.hour_spin.setValue(12)
        self.minute_spin.setValue(0)
        self.date_picker.setDate(QDate.currentDate())

    def show_context_menu(self, point):
        menu = QMenu(self)
        item = self.queue_list.itemAt(point)
        if item is None:
            return
        post_time, content = item.data(32)

        modify_action = QAction("Modify Post", self)
        modify_action.triggered.connect(lambda: self.modify_post(item, post_time, content))
        delete_action = QAction("Delete Post", self)
        delete_action.triggered.connect(lambda: self.delete_post(item))

        menu.addAction(modify_action)
        menu.addAction(delete_action)

        menu.exec(self.queue_list.mapToGlobal(point))

    def modify_post(self, item, post_time, content):
        self.text_box.setText(content)
        self.date_picker.setDate(post_time.date())
        self.hour_spin.setValue(post_time.hour)
        self.minute_spin.setValue(post_time.minute)

        row = self.queue_list.row(item)
        self.queue_list.takeItem(row)

        scheduled_posts[:] = [entry for entry in scheduled_posts if entry != (post_time, content)]

        modified_post_time = datetime.datetime.combine(self.date_picker.date().toPyDate(), datetime.time(self.hour_spin.value(), self.minute_spin.value()))
        modified_content = self.text_box.toPlainText().strip()
        scheduled_posts.append((modified_post_time, modified_content))

        print(f"Modified post: {modified_post_time}, {modified_content}")
        self.update_queue_display(f"🕒 {modified_post_time.strftime('%Y-%m-%d %H:%M')} — Queued", modified_post_time, modified_content)

    def delete_post(self, item):
        row = self.queue_list.row(item)
        self.queue_list.takeItem(row)

        post_time, content = item.data(32)
        scheduled_posts[:] = [entry for entry in scheduled_posts if entry != (post_time, content)]
        print(f"Deleted: {content} scheduled for {post_time}")

if __name__ == "__main__":
    app = QApplication(sys.argv)

    client = Client()
    while True:
        dialog = LoginDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            username, password = dialog.get_credentials()
            try:
                client.login(username, password)
                break  # Successful login
            except Exception as e:
                error_box = QMessageBox()
                error_box.setIcon(QMessageBox.Icon.Critical)
                error_box.setText("Login Failed")
                error_box.setInformativeText(str(e))
                error_box.setWindowTitle("Error")
                error_box.exec()
                continue  # Re-prompt for credentials
        else:
            sys.exit()  # User canceled login

    # Launch main window after successful login
    window = TrayApp(client)
    window.show()
    sys.exit(app.exec())

