from __future__ import absolute_import
import sys
import os
import json

from Deadline.Scripting import RepositoryUtils

repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(
    repo_path, "custom", "scripts", "General", "PoolManager"
)
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

try:
    from PySide2.QtWidgets import (
        QApplication,
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QAbstractItemView,
        QWidget,
        QLineEdit,
        QListWidget,
        QInputDialog,
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QIntValidator
except ImportError:
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QAbstractItemView,
        QWidget,
        QLineEdit,
        QListWidget,
        QInputDialog,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QIntValidator


class NightSlapUI(QDialog):
    def __init__(self, parent=None):
        super(NightSlapUI, self).__init__(parent)
        self.setup_ui()

    def setup_ui(self):

        print("Setting up UI")
        title = "Night auto slap config"
        self.setWindowTitle(title)
        self.setMinimumSize(500, 400)

        self.config_file = self.getConfigFile()
        self.min_time, self.max_time, self.project_exclude, self.user_exclude = (
            self.getConfigData()
        )

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Time Range Section
        self._create_time_range_section()
        self.seperator_line()

        # Create common exclude section layout
        self.exclude_layout = QHBoxLayout()

        # Project Exclude Section
        self._create_project_exclude_section()
        # User Exclude Section
        self._create_user_exclude_section()

        # Add exclude layout
        self.main_layout.addLayout(self.exclude_layout)

        # Seperate
        self.main_layout.addSpacing(5)
        self.seperator_line()
        self.main_layout.addSpacing(5)

        # Buttons Section
        self._create_buttons_section()

    def _create_time_range_section(self):

        time_text = QLabel("Detect jobs between: ")

        self.min_time_edit = QLineEdit(self)
        self.min_time_edit.setFixedWidth(40)
        self.min_time_edit.setValidator(QIntValidator())
        if self.min_time is not None:
            self.min_time_edit.setText(str(self.min_time))

        seperator_label = QLabel("and")

        self.max_time_edit = QLineEdit(self)
        self.max_time_edit.setFixedWidth(40)
        self.max_time_edit.setValidator(QIntValidator())
        if self.max_time is not None:
            self.max_time_edit.setText(str(self.max_time))

        time_layout = QHBoxLayout()
        time_layout.addWidget(time_text)
        time_layout.addWidget(self.min_time_edit)
        time_layout.addWidget(seperator_label)
        time_layout.addWidget(self.max_time_edit)
        time_layout.addStretch()

        self.main_layout.addLayout(time_layout)

    def _create_project_exclude_section(self):
        project_exclude_layout = QVBoxLayout()
        project_exclude_actions_layout = QHBoxLayout()

        project_label = QLabel("Project exclude list")

        self.project_exclude_widget = QListWidget()
        self.project_exclude_widget.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        project_exclude_add = QPushButton("Add")
        project_exclude_rm = QPushButton("Remove")
        project_exclude_add.clicked.connect(self.add_project_exclude)
        project_exclude_rm.clicked.connect(self.remove_project_exclude)
        project_exclude_actions_layout.addWidget(project_exclude_add)
        project_exclude_actions_layout.addWidget(project_exclude_rm)

        project_exclude_layout.addWidget(project_label)
        project_exclude_layout.addWidget(self.project_exclude_widget)
        project_exclude_layout.addLayout(project_exclude_actions_layout)

        self.update_project_exclude()

        self.exclude_layout.addLayout(project_exclude_layout)

    def _create_user_exclude_section(self):
        user_exclude_layout = QVBoxLayout()
        user_exclude_actions_layout = QHBoxLayout()

        user_label = QLabel("User exclude list")

        self.user_exclude_widget = QListWidget()
        self.user_exclude_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        user_exclude_add = QPushButton("Add")
        user_exclude_rm = QPushButton("Remove")
        user_exclude_add.clicked.connect(self.add_user_exclude)
        user_exclude_rm.clicked.connect(self.remove_user_exclude)
        user_exclude_actions_layout.addWidget(user_exclude_add)
        user_exclude_actions_layout.addWidget(user_exclude_rm)

        user_exclude_layout.addWidget(user_label)
        user_exclude_layout.addWidget(self.user_exclude_widget)
        user_exclude_layout.addLayout(user_exclude_actions_layout)

        self.update_user_exclude()

        self.exclude_layout.addLayout(user_exclude_layout)

    def seperator_line(self):
        separator = QWidget()
        separator.setStyleSheet("background-color: grey;")
        separator.setFixedHeight(1)
        self.main_layout.addWidget(separator)

    def add_project_exclude(self):
        text, ok = QInputDialog.getText(
            self,
            "Add project",
            "Add projects (separated by space)",
            QLineEdit.Normal,
            "",
        )
        if not (ok and text):
            return

        projects = text.split(" ")
        for project in projects:
            if self.project_exclude_widget.findItems(project, Qt.MatchExactly):
                continue
            self.project_exclude.append(project)

        self.update_project_exclude()

    def remove_project_exclude(self):
        for project_item in self.project_exclude_widget.selectedItems():
            project_name = project_item.text()
            self.project_exclude.remove(str(project_name))

        self.update_project_exclude()

    def add_user_exclude(self):
        text, ok = QInputDialog.getText(
            self, "Add user", "Add users (separated by space)", QLineEdit.Normal, ""
        )
        if not (ok and text):
            return

        users = text.split(" ")
        for user in users:
            if self.user_exclude_widget.findItems(user, Qt.MatchExactly):
                continue
            self.user_exclude.append(user)

        self.update_user_exclude()

    def remove_user_exclude(self):
        for user_item in self.user_exclude_widget.selectedItems():
            user_name = user_item.text()
            self.user_exclude.remove(str(user_name))

        self.update_user_exclude()

    def update_project_exclude(self):
        self.project_exclude_widget.clear()

        for project in self.project_exclude:
            if not self.project_exclude_widget.findItems(project, Qt.MatchExactly):
                self.project_exclude_widget.addItem(project)

    def update_user_exclude(self):
        self.user_exclude_widget.clear()

        for user in self.user_exclude:
            if not self.user_exclude_widget.findItems(user, Qt.MatchExactly):
                self.user_exclude_widget.addItem(user)

    def _create_buttons_section(self):

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.applyConfigData)

        default_button = QPushButton("Reset to default")
        default_button.clicked.connect(self.resetToDefault)

        button_layout = QHBoxLayout()
        button_layout.addWidget(apply_button)
        button_layout.addWidget(default_button)

        self.main_layout.addLayout(button_layout)

    def getConfigFile(self):

        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(base_dir, "NightSlapComp\config.json")

        return config_file

    def getConfigData(self):

        with open(self.config_file) as f:
            data = json.load(f)

        print(f"Dataaaaa: {data}")

        return (
            data["min_time"],
            data["max_time"],
            data["project_exclude"],
            data["user_exclude"],
        )

    def applyConfigData(self):

        print("Applying changes")

        with open(self.config_file, "r+") as f:
            data = json.load(f)
            data["min_time"] = int(self.min_time_edit.text())
            data["max_time"] = int(self.max_time_edit.text())
            data["project_exclude"] = self.project_exclude
            data["user_exclude"] = self.user_exclude

            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()

            print(f"Update data: {data}")

    def resetToDefault(self):
        self.min_time = 20
        self.max_time = 8
        self.project_exclude = []
        self.user_exclude = []

        if self.min_time is not None:
            self.min_time_edit.setText(str(self.min_time))
        if self.max_time is not None:
            self.max_time_edit.setText(str(self.max_time))

        self.update_project_exclude()
        self.update_user_exclude()

        self.applyConfigData()


def __main__():

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    print("Dialoguing")

    dialogue = NightSlapUI()
    dialogue.exec_()


if __name__ == "__main__":
    __main__()
