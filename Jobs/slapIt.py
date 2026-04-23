#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script Deadline: Récupère les dossiers de sortie des jobs sélectionnés
et génère un slap comp Nuke avec interface utilisateur
Fonctionne sur les jobs individuels ET les batches
"""

from __future__ import absolute_import

import os
import sys
import importlib

from Deadline.Scripting import ClientUtils, MonitorUtils, RepositoryUtils

# Ajoute le chemin du dossier General pour importer les modules
repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(repo_path, "custom", "scripts", "General")
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

# Import du module commun
import SlapCompCore

if "SlapCompCore" in sys.modules:
    importlib.reload(SlapCompCore)

# Import de l'UI Qt
import SlapCompUI_Qt

if "SlapCompUI_Qt" in sys.modules:
    importlib.reload(SlapCompUI_Qt)

from SlapCompUI_Qt import show_slap_comp_dialog


def __main__():
    # type: () -> None
    """Point d'entrée principal - workflow avec interface utilisateur."""

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

    if len(output_info) > 0:
        ClientUtils.LogText("\nOuverture interface...")
        dialog_result = show_slap_comp_dialog(output_info)

        if dialog_result:
            # Extrait les données et le mode de rendu
            ordered_output_info, render_mode = dialog_result

            ClientUtils.LogText("\nOrdre valide:")
            for item in ordered_output_info:
                layer_name = item.get(
                    "layer_name", os.path.basename(item.get("directory", "Unknown"))
                )
                merge_op = item.get("merge_operation", "over")
                ClientUtils.LogText(
                    f"  [{item['compositing_index']}] {layer_name} (merge: {merge_op})"
                )

            # Affiche le mode de rendu choisi
            render_mode_labels = {
                "none": "Ne pas lancer le rendu",
                "local": "Rendu local (ligne de commande)",
                "deadline": "Soumettre à Deadline",
            }
            ClientUtils.LogText(
                f"Mode de rendu: {render_mode_labels.get(render_mode, render_mode)}"
            )

            # Appelle le script Nuke
            SlapCompCore.call_nuke_script(ordered_output_info, render_mode)
        else:
            ClientUtils.LogText("\nAnnule")

    return output_info


if __name__ == "__main__":
    __main__()
