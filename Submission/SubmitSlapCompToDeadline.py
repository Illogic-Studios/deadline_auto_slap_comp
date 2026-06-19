#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de soumission Deadline pour les Slap Comp Nuke
"""

from __future__ import absolute_import
import os
import tempfile
import subprocess

PYTHON_JOB_POSTJOB_SCRIPT = r"R:\devAndrew\Deadline\PublishToShotgridPostJob\publishToSg.py"

def submit_slap_comp_job(
    nk_path,
    first_frame,
    last_frame,
    dependency_job_ids=None,
    pool="nuke",
    group="none",
    priority=50,
    job_name=None,
    render_dir=None,
    render_filename=None,
):
    """
    Soumet un job Deadline pour rendre un slap comp Nuke.

    Args:
        nk_path (str): Chemin du fichier .nk à rendre
        first_frame (int): Première frame
        last_frame (int): Dernière frame
        dependency_job_ids (list): Liste des IDs de jobs dont dépend ce job
        pool (str): Pool Deadline (défaut: "nuke")
        group (str): Group Deadline (défaut: "none")
        priority (int): Priorité du job (défaut: 50)
        job_name (str): Nom du job (optionnel, extrait du nom du fichier .nk si non fourni)
        render_dir (str): Dossier de rendu (optionnel, pour mode Prism)
        render_filename (str): Nom du fichier de rendu (optionnel, pour mode Prism)

    Returns:
        str: Job ID du job soumis, ou None si échec
    """
    # Détermine le nom du job
    if not job_name:
        job_name = os.path.splitext(os.path.basename(nk_path))[0]

    # Calcule le chunk size (5 frames par tâche)
    total_frames = last_frame - first_frame + 1
    chunk_size = 20  # Divise le job en tâches de x frames

    # Prépare les dépendances
    dependencies_str = ""
    if dependency_job_ids:
        # Filtre les None et crée une liste séparée par des virgules
        valid_ids = [str(jid) for jid in dependency_job_ids if jid]
        if valid_ids:
            dependencies_str = ",".join(valid_ids)

    # Calcule le chemin de sortie
    # Si render_dir et render_filename fournis (mode Prism), les utiliser
    if render_dir and render_filename:
        output_directory = render_dir
        # Convertit le pattern %04d en ####
        output_filename = render_filename.replace("%04d", "####")
    else:
        # Mode fallback (même logique que create_slap_comp.py)
        nk_dir = os.path.dirname(nk_path)
        nk_basename = os.path.splitext(os.path.basename(nk_path))[0]
        output_directory = os.path.join(nk_dir, "renders")
        output_filename = f"{nk_basename}.####.exr"

    # Normalise les paths pour Deadline (utilise toujours /)
    output_directory = output_directory.replace("\\", "/")
    nk_path_normalized = nk_path.replace("\\", "/")

    # Crée les fichiers temporaires pour la soumission
    temp_dir = tempfile.gettempdir()
    job_info_file = os.path.join(temp_dir, "slapcomp_job_info.job")
    plugin_info_file = os.path.join(temp_dir, "slapcomp_plugin_info.job")

    try:
        # Écrit le fichier job info
        with open(job_info_file, "w") as f:
            f.write("Plugin=Nuke\n")
            f.write(f"Name={job_name}\n")
            f.write("Comment=Slap Comp Render\n")
            f.write("Department=Comp\n")
            f.write(f"Pool={pool}\n")
            f.write(f"SecondaryPool=\n")
            f.write(f"Group={group}\n")
            f.write(f"Priority={priority}\n")
            f.write("MachineLimit=0\n")
            f.write("TaskTimeoutMinutes=0\n")
            f.write("EnableAutoTimeout=False\n")
            f.write("ConcurrentTasks=2\n")
            f.write("LimitConcurrentTasksToNumberOfCpus=False\n")
            f.write("LimitGroups=\n")
            f.write(f"JobDependencies={dependencies_str}\n")
            f.write("OnJobComplete=Nothing\n")
            f.write(f"Frames={first_frame}-{last_frame}\n")
            f.write(f"ChunkSize={chunk_size}\n")
            f.write(f"OutputDirectory0={output_directory}\n")
            f.write(f"OutputFilename0={output_filename}\n")
            f.write(f"PostJobScript={PYTHON_JOB_POSTJOB_SCRIPT}\n")

        # Écrit le fichier plugin info
        with open(plugin_info_file, "w") as f:
            f.write(f"SceneFile={nk_path_normalized}\n")
            f.write("Version=15.1\n")  # Version de Nuke
            f.write("Threads=0\n")
            f.write("RamUse=0\n")
            f.write("BatchMode=True\n")
            f.write("BatchModeIsMovie=False\n")
            f.write("NukeX=False\n")
            f.write("UseGpu=False\n")
            f.write("RenderMode=Use Scene Settings\n")
            f.write("WriteNode=\n")  # Vide = rendre tous les Write nodes actifs
            f.write("ContinueOnError=False\n")

        # Détermine le chemin de deadlinecommand selon l'OS
        import platform

        if platform.system() == "Darwin":  # macOS
            deadlinecommand = (
                "/Applications/Thinkbox/Deadline10/Resources/deadlinecommand"
            )
        elif platform.system() == "Windows":
            deadlinecommand = (
                "C:\\Program Files\\Thinkbox\\Deadline10\\bin\\deadlinecommand.exe"
            )
        else:  # Linux
            deadlinecommand = "/opt/Thinkbox/Deadline10/bin/deadlinecommand"

        # Soumet le job via deadlinecommand
        cmd = [deadlinecommand, job_info_file, plugin_info_file]

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
        )
        stdout, stderr = process.communicate()

        # Nettoie les fichiers temporaires
        try:
            os.unlink(job_info_file)
            os.unlink(plugin_info_file)
        except:
            pass

        # Parse la sortie pour extraire le Job ID
        if process.returncode == 0:
            for line in stdout.splitlines():
                if line.startswith("JobID="):
                    job_id = line.split("=")[1].strip()
                    return job_id
            return None
        else:
            print(f"ERREUR soumission Deadline: {stderr}")
            return None

    except Exception as e:
        print(f"ERREUR: {str(e)}")
        # Nettoie en cas d'erreur
        try:
            os.unlink(job_info_file)
            os.unlink(plugin_info_file)
        except:
            pass
        return None
