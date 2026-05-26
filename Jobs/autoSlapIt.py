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

from Deadline.Scripting import ClientUtils, MonitorUtils, RepositoryUtils  # type: ignore

# Ajoute le chemin du dossier General pour importer SlapCompCore
repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(repo_path, "custom", "scripts", "General")
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

# Import du module commun
import slapcomp  # type: ignore  # noqa: E402

if "slapcomp" in sys.modules:
    importlib.reload(slapcomp)


def get_selected_jobs():
    selected_jobs = []

    selected_jobs = MonitorUtils.GetSelectedJobs()

    if not selected_jobs:
        ClientUtils.LogText("Aucun job ou batch selectionne")
        return

    return selected_jobs


def __main__():

    selected_jobs = get_selected_jobs()
    slapcomp.auto_slap(selected_jobs)


if __name__ == "__main__":
    __main__()
