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

from Deadline.Scripting import ClientUtils, MonitorUtils, RepositoryUtils  # type: ignore

# Ajoute le chemin du dossier General pour importer les modules
repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(repo_path, "custom", "scripts", "General")
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

# Import du module commun
import slapcomp  # type: ignore  # noqa: E402

if "slapcomp" in sys.modules:
    importlib.reload(slapcomp)


# TODO: Create common function to share with autoslapit
def get_jobs_to_process(selected_jobs):
    jobs_to_process = []
    processed_batches = set()

    ClientUtils.LogText(f"Selected jobs test: {selected_jobs}")

    for job in selected_jobs:
        batch_name = job.JobBatchName

        if batch_name and batch_name not in processed_batches:
            ClientUtils.LogText(f"Batch detecte: {batch_name}")
            batch_jobs = slapcomp.get_job_batch(batch_name)
            ClientUtils.LogText(f"  {len(batch_jobs)} job(s) dans le batch")
            jobs_to_process.extend(batch_jobs)
            processed_batches.add(batch_name)
        elif not batch_name:
            jobs_to_process.append(job)

    jobs_to_process = list({job.JobId: job for job in jobs_to_process}.values())
    return jobs_to_process


def handle_interface(output_info):
    ClientUtils.LogText("\nOuverture interface...")
    dialog_result = slapcomp.show_slap_comp_ui_dialog(output_info)

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
        slapcomp.call_nuke_script(ordered_output_info, render_mode)
    else:
        ClientUtils.LogText("\nAnnule")

    return output_info


def __main__():
    # type: () -> None
    """Point d'entrée principal - workflow avec interface utilisateur."""

    selected_jobs = slapcomp.get_selected_jobs()
    ClientUtils.LogText(f"Got selected jobs: {selected_jobs}")
    jobs_to_process = get_jobs_to_process(selected_jobs)

    output_info = slapcomp.get_output_dirs(jobs_to_process)
    if not output_info:
        return

    ClientUtils.LogText(f"\n{len(output_info)} sequence(s) trouvee(s)")
    handle_interface(output_info)


if __name__ == "__main__":
    __main__()
