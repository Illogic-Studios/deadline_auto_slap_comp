#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script Deadline: Version automatisée de slapIt
Récupère automatiquement les dernières versions complètes des rendus,
applique les presets de projet/shot, et soumet le slap comp à Deadline
Sans interface utilisateur - 1 click automation
"""

from __future__ import absolute_import

import os
import sys
import importlib

from Deadline.Scripting import ClientUtils, MonitorUtils, RepositoryUtils

# Ajoute le chemin du dossier General pour importer SlapCompCore
repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(repo_path, "custom", "scripts", "General")
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

# Import du module commun
import SlapCompCore

if "SlapCompCore" in sys.modules:
    importlib.reload(SlapCompCore)


def __main__():
    # type: () -> None
    """Point d'entrée principal - workflow automatisé."""

    selected_jobs = []

    selected_jobs = MonitorUtils.GetSelectedJobs()

    if not selected_jobs:
        try:
            selected_job_group = MonitorUtils.GetSelectedJobGroup()
            if selected_job_group:
                batch_name = selected_job_group.Name
                ClientUtils.LogText(f"Batch selectionne: {batch_name}")
                selected_jobs = SlapCompCore.get_job_batch(batch_name)
        except:
            pass

    if not selected_jobs:
        ClientUtils.LogText("Aucun job ou batch selectionne")
        return

    jobs_to_process = []
    processed_batches = set()

    for job in selected_jobs:
        batch_name = job.JobBatchName

        if batch_name and batch_name not in processed_batches:
            ClientUtils.LogText(f"Batch detecte: {batch_name}")
            batch_jobs = SlapCompCore.get_job_batch(batch_name)
            ClientUtils.LogText(f"  {len(batch_jobs)} job(s) dans le batch")
            jobs_to_process.extend(batch_jobs)
            processed_batches.add(batch_name)
        elif not batch_name:
            jobs_to_process.append(job)

    jobs_to_process = list({job.JobId: job for job in jobs_to_process}.values())

    output_info = SlapCompCore.get_output_dirs(jobs_to_process)

    ClientUtils.LogText(f"\n{len(output_info)} sequence(s) trouvee(s)")

    if len(output_info) == 0:
        ClientUtils.LogText("Aucune sequence trouvee")
        return

    # === AUTOMATION: Sélection automatique des dernières versions complètes ===
    ClientUtils.LogText(
        "\n=== Selection automatique des dernieres versions completes ==="
    )
    output_info = SlapCompCore.select_latest_complete_versions(output_info)

    if len(output_info) == 0:
        ClientUtils.LogText("Erreur: aucune version selectionnee")
        return

    # === AUTOMATION: Application automatique des presets ===
    ClientUtils.LogText("\n=== Application des presets ===")
    # Extrait project/sequence/shot du premier item
    first_info = output_info[0]
    project = first_info.get("project", "")
    sequence = first_info.get("sequence", "")
    shot = first_info.get("shot", "")

    # Charge et applique le preset
    preset_data = SlapCompCore.load_preset(project, sequence, shot)
    if preset_data:
        ordered_output_info = SlapCompCore.apply_preset_data(output_info, preset_data)
        ClientUtils.LogText("\nOrdre des layers applique depuis preset:")
        for idx, info in enumerate(ordered_output_info):
            layer_name = info.get("layer_name", "Unknown")
            merge_op = info.get("merge_operation", "over")
            ClientUtils.LogText(f"  [{idx}] {layer_name} (merge: {merge_op})")
    else:
        ordered_output_info = output_info
        ClientUtils.LogText("Utilisation ordre par defaut")

    # Ajoute les index de compositing
    for idx, item in enumerate(ordered_output_info):
        item["compositing_index"] = idx

    # === AUTOMATION: Soumission automatique à Deadline ===
    ClientUtils.LogText("\n=== Soumission automatique a Deadline ===")
    render_mode = "deadline"  # Force le mode Deadline

    ClientUtils.LogText("\nOrdre final:")
    for item in ordered_output_info:
        layer_name = item.get(
            "layer_name", os.path.basename(item.get("directory", "Unknown"))
        )
        merge_op = item.get("merge_operation", "over")
        ClientUtils.LogText(
            f"  [{item['compositing_index']}] {layer_name} (merge: {merge_op})"
        )

    ClientUtils.LogText(f"\nMode de rendu: Soumettre a Deadline")

    # Appelle le script Nuke
    SlapCompCore.call_nuke_script(ordered_output_info, render_mode)


if __name__ == "__main__":
    __main__()
