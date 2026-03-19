#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interface graphique Deadline pour configurer l'ordre de compositing du slap comp
"""

from __future__ import absolute_import
from Deadline.Scripting import ClientUtils
from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog

scriptDialog = None
output_info_global = []
dialog_accepted = False


def get_status_color(completion_percent):
    """Retourne la couleur HTML en fonction du taux de complétion."""
    if completion_percent == 0:
        return "#FF0000"  # Rouge
    elif completion_percent < 100:
        return "#FFA500"  # Orange
    else:
        return "#00FF00"  # Vert


def get_layer_name(info):
    """Extrait un nom lisible pour le layer."""
    layer_name = info.get('layer_name', 'Unknown')

    # Ajoute l'indicateur de source
    source = info.get('source', 'deadline')
    source_icon = "📋" if source == 'deadline' else "📁"

    # Affiche la version sélectionnée et sa complétion (NOM SIMPLE)
    if 'versions' in info and 'selected_version_index' in info:
        selected_idx = info['selected_version_index']
        selected_version = info['versions'][selected_idx]
        version = selected_version['version']
        completion = selected_version['completion_percent']
        status_icon = "✓" if completion == 100 else "⚠"

        return f"{source_icon} {layer_name} - {version} ({completion:.0f}%) {status_icon}"
    else:
        # Fallback pour ancienne structure
        return f"{source_icon} {layer_name}"


def on_move_up(*args):
    """Deplace le layer selectionne vers le haut."""
    global scriptDialog, output_info_global

    try:
        selected_text = scriptDialog.GetValue("LayerList")
        included_indices = get_included_indices()
        layer_names = [get_layer_name(output_info_global[idx]) for idx in included_indices]

        if selected_text not in layer_names:
            return

        # Index dans la liste filtrée
        filtered_index = layer_names.index(selected_text)

        if filtered_index <= 0:
            return

        # Index réels dans output_info_global
        real_index = included_indices[filtered_index]
        real_prev_index = included_indices[filtered_index - 1]

        # Échange dans output_info_global
        output_info_global[real_index], output_info_global[real_prev_index] = \
            output_info_global[real_prev_index], output_info_global[real_index]

        refresh_ui_controls()
        refresh_list()
        scriptDialog.SetValue("LayerList", get_layer_name(output_info_global[real_prev_index]))
        update_preview()
    except Exception as e:
        ClientUtils.LogText(f"Erreur move_up: {str(e)}")


def on_move_down(*args):
    """Deplace le layer selectionne vers le bas."""
    global scriptDialog, output_info_global

    try:
        selected_text = scriptDialog.GetValue("LayerList")
        included_indices = get_included_indices()
        layer_names = [get_layer_name(output_info_global[idx]) for idx in included_indices]

        if selected_text not in layer_names:
            return

        # Index dans la liste filtrée
        filtered_index = layer_names.index(selected_text)

        if filtered_index >= len(included_indices) - 1:
            return

        # Index réels dans output_info_global
        real_index = included_indices[filtered_index]
        real_next_index = included_indices[filtered_index + 1]

        # Échange dans output_info_global
        output_info_global[real_index], output_info_global[real_next_index] = \
            output_info_global[real_next_index], output_info_global[real_index]

        refresh_ui_controls()
        refresh_list()
        scriptDialog.SetValue("LayerList", get_layer_name(output_info_global[real_next_index]))
        update_preview()
    except Exception as e:
        ClientUtils.LogText(f"Erreur move_down: {str(e)}")


def on_version_changed(idx):
    """Met à jour le statut quand la version change."""
    global scriptDialog, output_info_global

    try:
        info = output_info_global[idx]
        if 'versions' not in info:
            return

        # Récupère la version sélectionnée
        selected_label = scriptDialog.GetValue(f"VersionCombo{idx}")

        # Trouve la version correspondante
        for v_idx, v in enumerate(info['versions']):
            completion = v['completion_percent']
            status_icon = "✓" if completion == 100 else "⚠"
            label = f"{v['version']} - {completion:.0f}% {status_icon}"

            if label == selected_label:
                # Met à jour selected_version_index dans output_info_global
                output_info_global[idx]['selected_version_index'] = v_idx

                # Met à jour le StatusLabel
                color = get_status_color(completion)
                status_text = f"<font color='{color}'>{v['status']} ({v['frames_completed']}/{v['frames_total']} frames)</font>"

                # Essaie plusieurs méthodes pour mettre à jour le contrôle
                try:
                    # Méthode 1: Tente d'accéder directement au contrôle
                    status_control = scriptDialog.GetControlByName(f"StatusLabel{idx}")
                    if status_control:
                        status_control.setText(status_text)
                    else:
                        # Méthode 2: Fallback sur SetValue
                        scriptDialog.SetValue(f"StatusLabel{idx}", status_text)
                except:
                    # Méthode 3: Si tout échoue, utilise SetValue classique
                    scriptDialog.SetValue(f"StatusLabel{idx}", status_text)

                ClientUtils.LogText(f"Status mis a jour pour layer {idx}: {v['status']} ({completion:.0f}%)")
                break
    except Exception as e:
        ClientUtils.LogText(f"Erreur on_version_changed({idx}): {str(e)}")
        import traceback
        traceback.print_exc()


def on_merge_op_changed(idx):
    """Met à jour le merge operation dans output_info_global quand la combobox change."""
    global scriptDialog, output_info_global

    try:
        # Récupère la valeur sélectionnée
        merge_op = scriptDialog.GetValue(f"MergeOpCombo{idx}")
        # Stocke dans output_info_global
        output_info_global[idx]['merge_operation'] = merge_op
        ClientUtils.LogText(f"Merge operation mis a jour pour layer {idx}: {merge_op}")
        # Met à jour le preview
        update_preview()
    except Exception as e:
        ClientUtils.LogText(f"Erreur on_merge_op_changed({idx}): {str(e)}")


def get_included_indices():
    """Retourne les indices des layers inclus."""
    global scriptDialog, output_info_global
    return [idx for idx in range(len(output_info_global))
            if scriptDialog.GetValue(f"IncludeCheck{idx}")]


def on_include_changed(*args):
    """Rafraîchit la liste de réordonnancement quand une checkbox change."""
    refresh_list()
    update_preview()


def refresh_list():
    """Rafraichit la liste des layers (seulement ceux inclus)."""
    global scriptDialog, output_info_global

    # Filtre uniquement les layers cochés
    layer_names = []
    for idx, info in enumerate(output_info_global):
        is_included = scriptDialog.GetValue(f"IncludeCheck{idx}")
        if is_included:
            layer_names.append(get_layer_name(info))

    scriptDialog.SetItems("LayerList", layer_names)


def refresh_ui_controls():
    """Synchronise les contrôles UI avec output_info_global après réordonnancement."""
    global scriptDialog, output_info_global

    for idx, info in enumerate(output_info_global):
        # Met à jour le nom du layer
        layer_name = info.get('layer_name', f'Layer{idx}')
        scriptDialog.SetValue(f"LayerName{idx}", layer_name)

        # Met à jour la source
        source = info.get('source', 'deadline')
        source_label = "Deadline" if source == 'deadline' else "Filesystem"
        scriptDialog.SetValue(f"SourceLabel{idx}", source_label)

        # Met à jour la checkbox included
        included = info.get('included', True)
        scriptDialog.SetValue(f"IncludeCheck{idx}", included)

        # Met à jour la version combo si elle existe
        if 'versions' in info:
            versions = info['versions']
            version_labels = []
            for v in versions:
                completion = v['completion_percent']
                status_icon = "✓" if completion == 100 else "⚠"
                version_labels.append(f"{v['version']} - {completion:.0f}% {status_icon}")

            selected_idx = info.get('selected_version_index', len(versions) - 1)
            selected_label = version_labels[selected_idx]
            scriptDialog.SetValue(f"VersionCombo{idx}", selected_label)

            # Met à jour le status
            selected_version = versions[selected_idx]
            completion = selected_version['completion_percent']
            color = get_status_color(completion)
            status_text = f"<font color='{color}'>{selected_version['status']} ({selected_version['frames_completed']}/{selected_version['frames_total']} frames)</font>"
            scriptDialog.SetValue(f"StatusLabel{idx}", status_text)

        # Met à jour le merge operation
        merge_op = info.get('merge_operation', 'over')
        scriptDialog.SetValue(f"MergeOpCombo{idx}", merge_op)


def update_preview():
    """Met a jour le preview de l'ordre de compositing."""
    global scriptDialog, output_info_global

    preview_lines = []

    # Utilise uniquement les layers inclus
    included_indices = get_included_indices()

    if len(included_indices) == 0:
        preview_lines.append("Aucun layer inclus")
    elif len(included_indices) == 1:
        idx = included_indices[0]
        preview_lines.append(f"Read: {get_layer_name(output_info_global[idx])}")
    else:
        # Premier layer
        first_idx = included_indices[0]
        preview_lines.append(f"Read[0]: {get_layer_name(output_info_global[first_idx])}")

        # Merges suivants
        for i in range(1, len(included_indices)):
            real_idx = included_indices[i]
            layer_name = get_layer_name(output_info_global[real_idx])

            # Récupère l'opération de fusion depuis output_info_global
            merge_op = output_info_global[real_idx].get('merge_operation', 'over')

            if i == 1:
                preview_lines.append(f"Merge{i} [{merge_op}] (A=Read[0], B=Read[{i}])")
            else:
                preview_lines.append(f"Merge{i} [{merge_op}] (A=Merge{i-1}, B=Read[{i}])")
            preview_lines.append(f"  Read[{i}]: {layer_name}")

    preview_text = "\n".join(preview_lines)
    scriptDialog.SetValue("PreviewText", preview_text)


def on_ok_clicked(*args):
    """Bouton OK clique."""
    global scriptDialog, dialog_accepted
    dialog_accepted = True
    scriptDialog.CloseDialog()


def on_cancel_clicked(*args):
    """Bouton Cancel clique."""
    global scriptDialog, dialog_accepted
    dialog_accepted = False
    scriptDialog.CloseDialog()


def show_slap_comp_dialog(output_info):
    """
    Fonction helper pour afficher le dialog depuis un autre script.
    
    Args:
        output_info (list): Liste de dicts avec les infos des layers
    
    Returns:
        list or None: Liste ordonnee des layers avec indices, ou None si annule
    """
    global scriptDialog, output_info_global, dialog_accepted
    
    output_info_global = output_info
    dialog_accepted = False

    scriptDialog = DeadlineScriptDialog()

    # Construit le titre avec les infos du projet
    title = "Slap Comp - Configuration"
    if output_info and len(output_info) > 0:
        first_info = output_info[0]
        project = first_info.get('project', '')
        sequence = first_info.get('sequence', '')
        shot = first_info.get('shot', '')
        if project and sequence and shot:
            title = f"Slap Comp - {project}_{sequence}_{shot}"

    scriptDialog.SetTitle(title)
    scriptDialog.SetSize(900, 600)  # Augmenté de 700 à 900 pour plus d'espace
    
    scriptDialog.AddGrid()
    scriptDialog.AddControlToGrid("InfoLabel", "LabelControl", "Configurez l'ordre et les versions des layers:", 0, 0, colSpan=6)
    scriptDialog.AddControlToGrid("Separator1", "SeparatorControl", "", 1, 0, colSpan=6)

    # Headers
    scriptDialog.AddControlToGrid("HeaderInclude", "LabelControl", "Include", 2, 0, expand=False)
    scriptDialog.AddControlToGrid("HeaderSource", "LabelControl", "Source", 2, 1, expand=False)
    scriptDialog.AddControlToGrid("HeaderLayer", "LabelControl", "Layer", 2, 2, expand=False)
    scriptDialog.AddControlToGrid("HeaderVersion", "LabelControl", "Version", 2, 3, expand=False)
    scriptDialog.AddControlToGrid("HeaderStatus", "LabelControl", "Status", 2, 4, expand=False)
    scriptDialog.AddControlToGrid("HeaderMergeOp", "LabelControl", "Merge Op", 2, 5, expand=False)
    
    # Pour chaque layer, créer une ligne avec ComboBox de version
    row = 3
    for idx, info in enumerate(output_info_global):
        layer_name = info.get('layer_name', f'Layer{idx}')
        source = info.get('source', 'deadline')
        included = info.get('included', True)

        # Checkbox pour inclure/exclure
        includeCheck = scriptDialog.AddControlToGrid(f"IncludeCheck{idx}", "CheckBoxControl", "", row, 0, expand=False)
        scriptDialog.SetValue(f"IncludeCheck{idx}", included)
        includeCheck.ValueModified.connect(on_include_changed)

        # Source (Deadline ou Filesystem)
        source_label = "Deadline" if source == 'deadline' else "Filesystem"
        scriptDialog.AddControlToGrid(f"SourceLabel{idx}", "LabelControl", source_label, row, 1, expand=False)

        # Nom du layer
        scriptDialog.AddControlToGrid(f"LayerName{idx}", "LabelControl", layer_name, row, 2, expand=False)
        
        # ComboBox pour sélectionner la version
        if 'versions' in info:
            versions = info['versions']
            version_labels = []
            for v in versions:
                completion = v['completion_percent']
                status_icon = "✓" if completion == 100 else "⚠"
                version_labels.append(f"{v['version']} - {completion:.0f}% {status_icon}")
            
            selected_idx = info.get('selected_version_index', len(versions) - 1)

            versionCombo = scriptDialog.AddComboControlToGrid(
                f"VersionCombo{idx}",
                "ComboControl",
                version_labels[selected_idx],
                version_labels,
                row, 3
            )
            # Fix: Utilise une fonction partielle pour capturer correctement l'index
            versionCombo.ValueModified.connect(lambda _idx=idx: on_version_changed(_idx))

            # Status détaillé de la version sélectionnée avec couleur
            selected_version = versions[selected_idx]
            completion = selected_version['completion_percent']
            color = get_status_color(completion)

            status_text = f"<font color='{color}'>{selected_version['status']} ({selected_version['frames_completed']}/{selected_version['frames_total']} frames)</font>"
            scriptDialog.AddControlToGrid(f"StatusLabel{idx}", "LabelControl", status_text, row, 4)

        # ComboBox pour le mode de fusion de ce layer
        merge_ops = ["over", "plus"]
        default_merge_op = info.get('merge_operation', 'over')
        mergeOpCombo = scriptDialog.AddComboControlToGrid(
            f"MergeOpCombo{idx}",
            "ComboControl",
            default_merge_op,
            merge_ops,
            row, 5
        )
        # Utilise une lambda qui ignore les arguments du signal et passe uniquement idx
        mergeOpCombo.ValueModified.connect(lambda *args, _idx=idx: on_merge_op_changed(_idx))

        row += 1

    scriptDialog.AddControlToGrid("Separator2", "SeparatorControl", "", row, 0, colSpan=6)
    row += 1

    # Boutons de réordonnement
    scriptDialog.AddControlToGrid("InfoReorder", "LabelControl", "Reordonnancement:", row, 0, colSpan=6)
    row += 1

    layer_names = [get_layer_name(info) for info in output_info_global]
    scriptDialog.AddControlToGrid("LayerList", "ListControl", "", row, 0, colSpan=6)
    scriptDialog.SetItems("LayerList", layer_names)
    row += 1

    moveUpButton = scriptDialog.AddControlToGrid("MoveUpButton", "ButtonControl", "Move Up", row, 0, expand=False)
    moveUpButton.ValueModified.connect(on_move_up)

    moveDownButton = scriptDialog.AddControlToGrid("MoveDownButton", "ButtonControl", "Move Down", row, 1, expand=False)
    moveDownButton.ValueModified.connect(on_move_down)
    row += 1

    scriptDialog.AddControlToGrid("Separator3", "SeparatorControl", "", row, 0, colSpan=6)
    row += 1

    # Preview
    scriptDialog.AddControlToGrid("PreviewLabel", "LabelControl", "Preview:", row, 0, colSpan=6)
    row += 1
    scriptDialog.AddControlToGrid("PreviewText", "MultiLineTextControl", "", row, 0, colSpan=6)
    row += 1

    scriptDialog.AddControlToGrid("Separator4", "SeparatorControl", "", row, 0, colSpan=6)
    row += 1

    # ComboBox pour le mode de rendu
    render_options = ["Ne pas lancer le rendu", "Rendu local (ligne de commande)", "Soumettre à Deadline"]
    scriptDialog.AddControlToGrid("RenderModeLabel", "LabelControl", "Mode de rendu:", row, 0, expand=False)
    scriptDialog.AddComboControlToGrid("RenderModeCombo", "ComboControl", "Ne pas lancer le rendu", render_options, row, 1, colSpan=2)
    row += 1

    scriptDialog.AddControlToGrid("Separator5", "SeparatorControl", "", row, 0, colSpan=6)
    row += 1

    # Boutons OK/Cancel
    okButton = scriptDialog.AddControlToGrid("OkButton", "ButtonControl", "OK", row, 0, expand=False)
    okButton.ValueModified.connect(on_ok_clicked)

    cancelButton = scriptDialog.AddControlToGrid("CancelButton", "ButtonControl", "Cancel", row, 1, expand=False)
    cancelButton.ValueModified.connect(on_cancel_clicked)

    scriptDialog.EndGrid()
    
    update_preview()

    # True = modal (bloque jusqu'a ce que l'utilisateur clique OK ou Cancel)
    scriptDialog.ShowDialog(True)

    # Verifie si OK a ete clique
    if dialog_accepted:
        # Récupère le mode de rendu sélectionné
        render_mode_label = scriptDialog.GetValue("RenderModeCombo")

        # Convertit le label en code
        render_mode = "none"
        if render_mode_label == "Rendu local (ligne de commande)":
            render_mode = "local"
        elif render_mode_label == "Soumettre à Deadline":
            render_mode = "deadline"

        # Récupère les versions sélectionnées et merge operations depuis les ComboBox
        result = []
        for index, info in enumerate(output_info_global):
            # Vérifie si le layer est inclus (checkbox cochée)
            is_included = scriptDialog.GetValue(f"IncludeCheck{index}")
            if not is_included:
                continue  # Skip ce layer
            if 'versions' in info:
                # Récupère la sélection de la ComboBox
                selected_version_label = scriptDialog.GetValue(f"VersionCombo{index}")
                # Trouve l'index de la version sélectionnée
                version_idx = 0
                for v_idx, v in enumerate(info['versions']):
                    completion = v['completion_percent']
                    status_icon = "✓" if completion == 100 else "⚠"
                    label = f"{v['version']} - {completion:.0f}% {status_icon}"
                    if label == selected_version_label:
                        version_idx = v_idx
                        break

                selected_version = info['versions'][version_idx]

                # Récupère le merge operation depuis output_info_global
                merge_operation = info.get('merge_operation', 'over')

                result.append({
                    'directory': selected_version['directory'],
                    'filename_pattern': selected_version['filename_pattern'],
                    'first_frame': selected_version['first_frame'],
                    'last_frame': selected_version['last_frame'],
                    'job_name': info.get('job_name', ''),
                    'compositing_index': len(result),  # Index dans l'ordre final
                    'version': selected_version['version'],
                    'job_id': selected_version.get('job_id'),
                    'job_ids': selected_version.get('job_ids', [selected_version.get('job_id')]),  # Pour les dépendances
                    'merge_operation': merge_operation
                })
            else:
                # Fallback ancienne structure
                # Récupère le merge operation depuis output_info_global
                merge_operation = info.get('merge_operation', 'over')

                result.append({
                    'directory': info['directory'],
                    'filename_pattern': info['filename_pattern'],
                    'first_frame': info['first_frame'],
                    'last_frame': info['last_frame'],
                    'job_name': info.get('job_name', ''),
                    'compositing_index': len(result),  # Index dans l'ordre final
                    'job_id': info.get('job_id'),
                    'job_ids': info.get('job_ids', [info.get('job_id')]),  # Pour les dépendances
                    'merge_operation': merge_operation
                })

        # Retourne un tuple (result, render_mode)
        # Chaque élément de result contient maintenant son propre 'merge_operation'
        return (result, render_mode)
    else:
        return None