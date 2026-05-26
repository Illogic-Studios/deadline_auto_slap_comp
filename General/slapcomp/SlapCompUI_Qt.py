#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interface graphique Qt pour configurer le slap comp
Version simplifiée avec boutons de réordonnancement
"""

from __future__ import absolute_import
import sys
import os
import json

# Imports Deadline
from Deadline.Scripting import ClientUtils, RepositoryUtils

# Import module commun
repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(repo_path, "custom", "scripts", "General")
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

import SlapCompCore

# Imports Qt (compatible PySide2 et PyQt5)
try:
    from PySide2.QtWidgets import (
        QApplication,
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QTableWidget,
        QTableWidgetItem,
        QPushButton,
        QLabel,
        QCheckBox,
        QComboBox,
        QHeaderView,
        QAbstractItemView,
        QWidget,
        QMessageBox,
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QColor
except ImportError:
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QTableWidget,
        QTableWidgetItem,
        QPushButton,
        QLabel,
        QCheckBox,
        QComboBox,
        QHeaderView,
        QAbstractItemView,
        QWidget,
        QMessageBox,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor


# Variables globales
_dialog_instance = None


def get_status_color(completion_percent):
    """Retourne la couleur QColor en fonction du taux de complétion."""
    if completion_percent == 0:
        return QColor(200, 50, 50)  # Rouge foncé
    elif completion_percent < 100:
        return QColor(255, 140, 0)  # Orange foncé
    else:
        return QColor(50, 180, 50)  # Vert foncé


class SlapCompDialog(QDialog):
    """Dialog Qt pour configurer le slap comp avec boutons de réordonnancement."""

    def __init__(self, output_info, parent=None):
        super(SlapCompDialog, self).__init__(parent)
        self.output_info = output_info
        self.dialog_accepted = False

        # Extrait project/sequence/shot pour les presets
        self.project = ""
        self.sequence = ""
        self.shot = ""
        if output_info and len(output_info) > 0:
            first_info = output_info[0]
            self.project = first_info.get("project", "")
            self.sequence = first_info.get("sequence", "")
            self.shot = first_info.get("shot", "")

        self.setup_ui()
        self.populate_table()

        # Charge le preset automatiquement au démarrage
        self.load_and_apply_preset()

    def setup_ui(self):
        """Configure l'interface utilisateur."""
        # Titre avec infos du projet
        title = "Slap Comp - Configuration"
        if self.output_info and len(self.output_info) > 0:
            first_info = self.output_info[0]
            project = first_info.get("project", "")
            sequence = first_info.get("sequence", "")
            shot = first_info.get("shot", "")
            if project and sequence and shot:
                title = f"Slap Comp - {project}_{sequence}_{shot}"

        self.setWindowTitle(title)
        self.setMinimumSize(1000, 600)

        # Layout principal
        main_layout = QVBoxLayout(self)

        # Labels d'instructions
        info_label = QLabel(
            "Sélectionnez une ligne et utilisez les boutons pour réordonner les layers:"
        )
        info_label.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 5px;")
        main_layout.addWidget(info_label)

        order_label = QLabel(
            "Layers empilés du haut (background) vers le bas (foreground)"
        )
        order_label.setStyleSheet(
            "font-style: italic; font-size: 10pt; padding: 2px 5px; color: #666;"
        )
        main_layout.addWidget(order_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Include", "Source", "Layer", "Version", "Status", "Merge Op"]
        )

        # Configuration de la sélection
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)

        # Configuration des colonnes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Include
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Source
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Layer
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Version
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Status
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Merge Op

        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(35)

        main_layout.addWidget(self.table)

        # Boutons de réordonnancement
        reorder_layout = QHBoxLayout()

        self.move_up_button = QPushButton("⬆ Move Up")
        self.move_up_button.clicked.connect(self.on_move_up)
        reorder_layout.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("⬇ Move Down")
        self.move_down_button.clicked.connect(self.on_move_down)
        reorder_layout.addWidget(self.move_down_button)

        reorder_layout.addStretch()

        # Boutons de gestion des presets
        self.save_preset_button = QPushButton("💾 Save Preset")
        self.save_preset_button.clicked.connect(self.on_save_preset)
        reorder_layout.addWidget(self.save_preset_button)

        self.load_preset_button = QPushButton("📂 Load Preset")
        self.load_preset_button.clicked.connect(self.on_load_preset)
        reorder_layout.addWidget(self.load_preset_button)

        main_layout.addLayout(reorder_layout)

        # Séparateur
        separator1 = QLabel()
        separator1.setFrameStyle(QLabel.HLine | QLabel.Sunken)
        main_layout.addWidget(separator1)

        # Mode de rendu
        render_layout = QHBoxLayout()
        render_label = QLabel("Mode de rendu:")
        render_layout.addWidget(render_label)

        self.render_combo = QComboBox()
        self.render_combo.addItems(
            [
                "Ne pas lancer le rendu",
                "Rendu local (ligne de commande)",
                "Soumettre à Deadline",
            ]
        )
        render_layout.addWidget(self.render_combo)
        render_layout.addStretch()

        main_layout.addLayout(render_layout)

        # Séparateur
        separator2 = QLabel()
        separator2.setFrameStyle(QLabel.HLine | QLabel.Sunken)
        main_layout.addWidget(separator2)

        # Boutons OK/Cancel
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.on_ok_clicked)
        button_layout.addWidget(self.ok_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        button_layout.addWidget(self.cancel_button)

        main_layout.addLayout(button_layout)

    def populate_table(self):
        """Remplit la table avec les données des layers."""
        self.table.setRowCount(len(self.output_info))

        for row_idx, info in enumerate(self.output_info):
            self.create_row(row_idx, info)

    def create_row(self, row_idx, info):
        """Crée une ligne de la table avec tous les widgets."""
        # Colonne 0: Include checkbox
        include_widget = QWidget()
        include_layout = QHBoxLayout(include_widget)
        include_layout.setContentsMargins(0, 0, 0, 0)
        include_layout.setAlignment(Qt.AlignCenter)

        include_check = QCheckBox()
        include_check.setChecked(info.get("included", True))
        include_check.stateChanged.connect(self.on_data_changed)
        include_layout.addWidget(include_check)

        self.table.setCellWidget(row_idx, 0, include_widget)

        # Colonne 1: Source (Deadline ou Filesystem)
        source = info.get("source", "deadline")
        source_label = "Deadline" if source == "deadline" else "Filesystem"
        source_item = QTableWidgetItem(source_label)
        source_item.setFlags(source_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row_idx, 1, source_item)

        # Colonne 2: Layer name
        layer_name = info.get("layer_name", f"Layer{row_idx}")
        layer_item = QTableWidgetItem(layer_name)
        layer_item.setFlags(layer_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row_idx, 2, layer_item)

        # Colonne 3: Version combo
        if "versions" in info:
            versions = info["versions"]
            version_combo = QComboBox()

            version_labels = []
            for v in versions:
                completion = v["completion_percent"]
                status_icon = "✓" if completion == 100 else "⚠"
                version_labels.append(
                    f"{v['version']} - {completion:.0f}% {status_icon}"
                )

            version_combo.addItems(version_labels)

            selected_idx = info.get("selected_version_index", len(versions) - 1)
            version_combo.setCurrentIndex(selected_idx)
            version_combo.currentIndexChanged.connect(
                lambda idx, row=row_idx: self.on_version_changed(row, idx)
            )

            self.table.setCellWidget(row_idx, 3, version_combo)

            # Colonne 4: Status avec couleur
            selected_version = versions[selected_idx]
            completion = selected_version["completion_percent"]
            status_text = f"{selected_version['status']} ({selected_version['frames_completed']}/{selected_version['frames_total']} frames)"

            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setBackground(get_status_color(completion))
            self.table.setItem(row_idx, 4, status_item)
        else:
            # Pas de versions disponibles
            no_version = QTableWidgetItem("N/A")
            no_version.setFlags(no_version.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 3, no_version)

            no_status = QTableWidgetItem("N/A")
            no_status.setFlags(no_status.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 4, no_status)

        # Colonne 5: Merge operation
        merge_combo = QComboBox()
        merge_combo.addItems(["over", "plus"])

        default_merge_op = info.get("merge_operation", "over")
        merge_combo.setCurrentText(default_merge_op)
        merge_combo.currentTextChanged.connect(self.on_data_changed)

        self.table.setCellWidget(row_idx, 5, merge_combo)

    def on_version_changed(self, row, version_idx):
        """Callback quand une version est changée."""
        # Met à jour le status
        info = self.get_row_info(row)
        if "versions" in info and version_idx < len(info["versions"]):
            selected_version = info["versions"][version_idx]
            completion = selected_version["completion_percent"]
            status_text = f"{selected_version['status']} ({selected_version['frames_completed']}/{selected_version['frames_total']} frames)"

            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setBackground(get_status_color(completion))
            self.table.setItem(row, 4, status_item)

    def on_data_changed(self):
        """Callback générique quand une donnée change."""
        # Peut être utilisé pour mettre à jour un preview si nécessaire
        pass

    def get_row_info(self, row):
        """Récupère l'info originale pour une ligne donnée."""
        # Trouve l'info correspondante en comparant le layer_name
        layer_item = self.table.item(row, 2)
        if layer_item:
            layer_name = layer_item.text()
            for info in self.output_info:
                if info.get("layer_name", "") == layer_name:
                    return info
        return {}

    def on_move_up(self):
        """Déplace la ligne sélectionnée vers le haut."""
        current_row = self.table.currentRow()

        if current_row <= 0:
            return  # Déjà en haut ou aucune sélection

        # Échange dans output_info
        new_row = current_row - 1
        self.output_info[current_row], self.output_info[new_row] = (
            self.output_info[new_row],
            self.output_info[current_row],
        )

        # Reconstruit la table
        self.rebuild_table()

        # Re-sélectionne la ligne déplacée
        self.table.selectRow(new_row)

        ClientUtils.LogText(f"Layer déplacé: ligne {current_row} -> {new_row}")

    def on_move_down(self):
        """Déplace la ligne sélectionnée vers le bas."""
        current_row = self.table.currentRow()

        if current_row < 0 or current_row >= self.table.rowCount() - 1:
            return  # Déjà en bas ou aucune sélection

        # Échange dans output_info
        new_row = current_row + 1
        self.output_info[current_row], self.output_info[new_row] = (
            self.output_info[new_row],
            self.output_info[current_row],
        )

        # Reconstruit la table
        self.rebuild_table()

        # Re-sélectionne la ligne déplacée
        self.table.selectRow(new_row)

        ClientUtils.LogText(f"Layer déplacé: ligne {current_row} -> {new_row}")

    def rebuild_table(self):
        """Reconstruit toute la table à partir de output_info."""
        # Vide la table
        self.table.clearContents()
        self.table.setRowCount(0)

        # Recrée toutes les lignes
        self.populate_table()

    # ========== Gestion des Presets ==========

    def get_preset_dir(self):
        """Retourne le répertoire des presets pour ce projet."""
        return SlapCompCore.get_preset_dir(self.project)

    def get_current_layer_order(self):
        """Extrait l'ordre actuel des layers et leurs merge operations depuis l'UI."""
        layer_order = []
        default_merge_ops = {}

        # Parcourt les lignes de la table pour récupérer l'ordre et les merge ops actuels
        for row_idx in range(self.table.rowCount()):
            layer_item = self.table.item(row_idx, 2)  # Colonne Layer
            if layer_item:
                layer_name = layer_item.text()
                layer_order.append(layer_name)

                # Récupère le merge operation depuis la combobox
                merge_combo = self.table.cellWidget(row_idx, 5)
                if merge_combo and isinstance(merge_combo, QComboBox):
                    merge_op = merge_combo.currentText()
                    if merge_op != "over":  # Enregistre seulement les non-default
                        default_merge_ops[layer_name] = merge_op

        return {"layer_order": layer_order, "default_merge_ops": default_merge_ops}

    def load_and_apply_preset(self):
        """Charge et applique automatiquement le preset au démarrage."""
        # Utilise la fonction du module commun pour charger le preset
        preset_data = SlapCompCore.load_preset(self.project, self.sequence, self.shot)

        # Applique le preset si trouvé
        if preset_data:
            self.apply_preset(preset_data)

    def apply_preset(self, preset_data):
        """Applique le preset: réordonne les layers et applique merge ops."""
        # Utilise la fonction du module commun
        self.output_info = SlapCompCore.apply_preset_data(self.output_info, preset_data)
        self.rebuild_table()

    def on_save_preset(self):
        """Sauvegarde le preset: demande à l'utilisateur Project ou Shot."""
        preset_dir = self.get_preset_dir()
        if not preset_dir:
            QMessageBox.warning(self, "Erreur", "Impossible de déterminer le projet")
            return

        # Crée le répertoire si nécessaire
        if not os.path.exists(preset_dir):
            try:
                os.makedirs(preset_dir)
            except Exception as e:
                QMessageBox.critical(
                    self, "Erreur", f"Impossible de créer le répertoire:\n{str(e)}"
                )
                return

        # Crée un message box personnalisé avec boutons clairs
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Save Preset")
        msg_box.setText("Choisissez où sauvegarder le preset:")

        # Boutons personnalisés
        project_button = msg_box.addButton(
            "Save Project Preset", QMessageBox.AcceptRole
        )
        shot_button = msg_box.addButton("Save Shot Preset", QMessageBox.AcceptRole)
        cancel_button = msg_box.addButton("Cancel", QMessageBox.RejectRole)

        msg_box.setDefaultButton(cancel_button)
        msg_box.exec_()

        clicked_button = msg_box.clickedButton()

        if clicked_button == cancel_button:
            return

        # Récupère l'ordre actuel
        preset_data = self.get_current_layer_order()

        try:
            if clicked_button == project_button:  # Project
                result = SlapCompCore.save_preset_project(self.project, preset_data)
                if result:
                    QMessageBox.information(
                        self, "Succès", f"Preset projet sauvegardé:\n{result}"
                    )
                else:
                    QMessageBox.critical(
                        self, "Erreur", "Erreur lors de la sauvegarde du preset projet"
                    )

            elif clicked_button == shot_button:  # Shot
                if not self.shot:
                    QMessageBox.warning(self, "Erreur", "Aucun shot détecté")
                    return

                shot_key = SlapCompCore.save_preset_shot(
                    self.project, self.sequence, self.shot, preset_data
                )
                if shot_key:
                    QMessageBox.information(
                        self, "Succès", f"Preset shot sauvegardé pour: {shot_key}"
                    )
                else:
                    QMessageBox.critical(
                        self, "Erreur", "Erreur lors de la sauvegarde du preset shot"
                    )

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur sauvegarde preset:\n{str(e)}")
            ClientUtils.LogText(f"Erreur sauvegarde preset: {str(e)}")

    def on_load_preset(self):
        """Recharge le preset manuellement."""
        self.load_and_apply_preset()
        QMessageBox.information(self, "Preset", "Preset rechargé")

    def on_ok_clicked(self):
        """Bouton OK cliqué."""
        self.dialog_accepted = True
        self.accept()

    def on_cancel_clicked(self):
        """Bouton Cancel cliqué."""
        self.dialog_accepted = False
        self.reject()

    def get_result(self):
        """Retourne les données dans le format attendu par slapIt.py."""
        if not self.dialog_accepted:
            return None

        # Récupère le mode de rendu
        render_mode_label = self.render_combo.currentText()
        render_mode = "none"
        if render_mode_label == "Rendu local (ligne de commande)":
            render_mode = "local"
        elif render_mode_label == "Soumettre à Deadline":
            render_mode = "deadline"

        result = []

        # Parcourt les lignes dans l'ordre actuel de la table
        for row_idx in range(self.table.rowCount()):
            # Vérifie si inclus
            include_widget = self.table.cellWidget(row_idx, 0)
            if include_widget:
                include_check = include_widget.findChild(QCheckBox)
                if include_check and not include_check.isChecked():
                    continue  # Skip ce layer

            # Récupère l'info originale
            info = self.get_row_info(row_idx)
            if not info:
                continue

            # Récupère la version sélectionnée
            if "versions" in info:
                version_combo = self.table.cellWidget(row_idx, 3)
                if version_combo and isinstance(version_combo, QComboBox):
                    version_idx = version_combo.currentIndex()
                    selected_version = info["versions"][version_idx]

                    # Récupère le merge operation
                    merge_combo = self.table.cellWidget(row_idx, 5)
                    merge_operation = "over"
                    if merge_combo and isinstance(merge_combo, QComboBox):
                        merge_operation = merge_combo.currentText()

                    # Construit le nom du layer pour job_name
                    layer_name = info.get("layer_name", "Unknown")
                    job_name = f"{layer_name}_{selected_version['version']}"

                    result.append(
                        {
                            "directory": selected_version["directory"],
                            "pattern": selected_version.get("pattern", ""),
                            "first_frame": selected_version["first_frame"],
                            "last_frame": selected_version["last_frame"],
                            "layer_name": layer_name,
                            "compositing_index": len(result),
                            "version": selected_version["version"],
                            "merge_operation": merge_operation,
                            "project": info.get("project", ""),
                            "sequence": info.get("sequence", ""),
                            "shot": info.get("shot", ""),
                            "job_id": selected_version.get("job_id"),
                            "job_ids": selected_version.get("job_ids", []),
                        }
                    )
            else:
                # Fallback ancienne structure
                merge_combo = self.table.cellWidget(row_idx, 5)
                merge_operation = "over"
                if merge_combo and isinstance(merge_combo, QComboBox):
                    merge_operation = merge_combo.currentText()

                result.append(
                    {
                        "directory": info["directory"],
                        "filename_pattern": info["filename_pattern"],
                        "first_frame": info["first_frame"],
                        "last_frame": info["last_frame"],
                        "job_name": info.get("job_name", ""),
                        "compositing_index": len(result),
                        "job_id": info.get("job_id"),
                        "job_ids": info.get("job_ids", [info.get("job_id")]),
                        "merge_operation": merge_operation,
                    }
                )

        return (result, render_mode)


def show_slap_comp_dialog(output_info):
    """
    Affiche le dialog Qt pour configurer le slap comp.

    Args:
        output_info (list): Liste de dicts avec les infos des layers

    Returns:
        tuple or None: (result_list, render_mode) ou None si annulé
    """
    global _dialog_instance

    # Transforme les données pour l'UI (regroupe par layer avec versions[])
    grouped_output_info = SlapCompCore.group_output_info_for_ui(output_info)

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    _dialog_instance = SlapCompDialog(grouped_output_info)
    _dialog_instance.exec_()

    return _dialog_instance.get_result()
