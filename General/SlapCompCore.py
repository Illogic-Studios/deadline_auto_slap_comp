#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SlapCompCore - Module commun pour la génération de slap comps Nuke
Partagé entre slapIt.py et autoSlapIt.py

Contient toutes les fonctions de logique métier:
- Manipulation de chemins Nuke
- Intégration Deadline (jobs, batches, versioning)
- Détection de séquences d'images
- Parsing de la structure Prism
- Génération et soumission de scripts Nuke
- Gestion des presets
"""

from __future__ import absolute_import

import os
import sys
import re
import subprocess
import tempfile
import json
import datetime
import inspect
import configparser
from Deadline.Scripting import ClientUtils, RepositoryUtils


# ============================================================================
# NOTES DE DÉVELOPPEMENT
# ============================================================================
# Si support Houdini/Husk ajouté à l'avenir, implémenter convert_padding_to_nuke()
# pour convertir patterns $F4 (Houdini) et %04d (Maya) vers format Nuke (####).
# Actuellement, tous les patterns sont générés automatiquement en format Nuke
# par detect_image_sequence_info() qui scanne le filesystem.
# ============================================================================


# ============================================================================
# SECTION 1: UTILITIES (NUKE)
# ============================================================================


def normalize_path_for_nuke(path):
    """
    Convertit les backslashes Windows en forward slashes pour Nuke.

    Args:
        path (str): Chemin avec backslashes ou forward slashes

    Returns:
        str: Chemin avec forward slashes uniquement
    """
    if path:
        return path.replace("\\", "/")
    return path

def get_file_path_from_config(attr_name):
    current_directory = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(current_directory, "path_config.ini")

    config = configparser.ConfigParser()
    try: 
        config.read(config_file)
        file_path = config.get("DEFAULT", attr_name)
    except Exception:    
        file_path = None
        print(f"{attr_name} COULD NOT BE ACCESSED OR {config_file} WAS NOT FOUND")
    
    return file_path

def addLog(message):
    """Add log message to both console and file only when called from NightAutoSlapComp.py"""

    ClientUtils.LogText(message)

    # check call stack for NightAutoSlapComp.py

    log_dir = get_file_path_from_config("LOG_DIR")
    if not log_dir: 
        return

    filename = "SlapDependencyDebug" + datetime.datetime.now().strftime(
        "%Y%m%d"
    )
    log_file = os.path.join(log_dir, filename + ".log")

    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    with open(log_file, "a") as f:
        f.write(f"{datetime.datetime.now()} - {message}\n")


# ============================================================================
# SECTION 2: DEADLINE INTEGRATION
# ============================================================================


def get_nuke_executable():
    """
    Récupère le chemin de l'exécutable Nuke depuis la config Deadline.

    Returns:
        str: Chemin vers nuke.exe ou fallback
    """
    try:
        nuke_plugin = RepositoryUtils.GetPluginDirectory("Nuke")
        nuke_plugin_info = os.path.join(nuke_plugin, "Nuke.param")

        if os.path.exists(nuke_plugin_info):
            with open(nuke_plugin_info, "r") as f:
                for line in f:
                    if line.startswith("RenderExecutable"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            nuke_path = parts[1].strip()
                            if os.path.exists(nuke_path):
                                addLog(f"Nuke executable trouve: {nuke_path}")
                                return nuke_path
    except Exception as e:
        addLog(f"Erreur lecture config Nuke: {str(e)}")

    # Fallback
    fallback_path = get_file_path_from_config("FALLBACK_NUKE")
    addLog(f"Utilisation fallback Nuke: {fallback_path}")
    return fallback_path


def get_job_batch(batch_name):
    """
    Récupère tous les jobs d'un batch Deadline.

    Args:
        batch_name (str): Nom du batch

    Returns:
        list: Liste des jobs du batch
    """
    all_jobs = RepositoryUtils.GetJobs(True)  # True = include completed
    batch_jobs = [job for job in all_jobs if job.JobBatchName == batch_name]
    return batch_jobs


def remove_suffix(job_name):
    # TODO : clean this up
    if job_name.endswith("__OPTI1024"):
        job_name = job_name[: -len("__OPTI1024")]

    if job_name.endswith("_high_prio_render"):
        job_name = job_name[: -len("_high_prio_render")]
    elif job_name.endswith("_render"):
        job_name = job_name[: -len("_render")]

    return job_name


def group_high_prio_and_render_jobs(jobs):
    """
    Groupe les jobs _high_prio_render et _render qui correspondent à la même version.
    Puis cherche TOUTES les versions disponibles dans Deadline pour chaque layer.

    Args:
        jobs (list): Liste de jobs Deadline

    Returns:
        dict: Mapping (base_name, version) -> liste de jobs associés
              base_name = nom du layer sans version ni suffixe render
    """
    if not jobs:
        return {}

    # Étape 1: Extraire les base_names uniques des jobs sélectionnés
    base_names_set = set()

    for job in jobs:
        job_name = job.JobName

        # Retire les suffixes
        clean_name = remove_suffix(job_name)

        # Extrait base_name
        version_match = re.search(r"(.+?)_v(\d+)$", clean_name)
        if version_match:
            base_name = version_match.group(1)
            base_names_set.add(base_name)

    if not base_names_set:
        addLog("  Aucun base_name trouvé avec pattern _v###")
        return {}

    addLog(f"  Base names trouvés: {len(base_names_set)}")
    for bn in base_names_set:
        addLog(f"    - {bn}")

    # Étape 2: Pour chaque base_name, chercher TOUTES les versions dans Deadline
    addLog("  Recherche de TOUTES les versions dans Deadline...")
    all_jobs = RepositoryUtils.GetJobs(True)  # True = include completed

    final_grouped = {}

    for base_name in base_names_set:
        # Trouve TOUTES les versions de ce base_name
        matching_versions = {}

        for job in all_jobs:
            job_name = job.JobName

            # Retire les suffixes
            clean_name = remove_suffix(job_name)

            # Vérifie si ce job matche notre base_name
            version_match = re.search(r"(.+?)_v(\d+)$", clean_name)

            if version_match:
                job_base_name = version_match.group(1)
                job_version = int(version_match.group(2))

                if job_base_name == base_name:
                    # Ce job correspond!
                    version_key = (base_name, job_version)
                    if version_key not in matching_versions:
                        matching_versions[version_key] = []
                    matching_versions[version_key].append(job)

        addLog(
            f"    Base '{base_name}': {len(matching_versions)} version(s) trouvée(s)"
        )
        for (bn, ver), jobs_list in sorted(
            matching_versions.items(), key=lambda x: x[0][1]
        ):
            addLog(f"      - v{ver:03d} ({len(jobs_list)} job(s))")

        # Ajoute toutes les versions trouvées
        final_grouped.update(matching_versions)

    return final_grouped


def get_combined_frame_range(jobs):
    """
    Calcule le frame range combiné de plusieurs jobs.

    Args:
        jobs (list): Liste de jobs Deadline

    Returns:
        tuple: (first_frame, last_frame)
    """
    all_frames = []

    for job in jobs:
        frames_list = job.JobFramesList
        if frames_list:
            # JobFramesList retourne un tableau d'entiers directement
            if hasattr(frames_list, "__iter__"):
                all_frames.extend(frames_list)

    if all_frames:
        return (min(all_frames), max(all_frames))
    return (1, 1)


def get_combined_job_completion(jobs):
    """
    Calcule la complétion combinée de plusieurs jobs (high_prio + render).

    Args:
        jobs (list): Liste de jobs Deadline associés

    Returns:
        dict: {
            'status': str,
            'completion': int (0-100),
            'completed_frames': int,
            'total_frames': int
        }
    """
    total_completed = 0
    total_frames = 0
    all_completed = True
    any_failed = False

    for job in jobs:
        frames_list = job.JobFramesList
        completed_list = job.JobCompletedTasks

        # Count total frames (JobFramesList est un tableau d'entiers)
        job_frames = 0
        if frames_list and hasattr(frames_list, "__iter__"):
            job_frames = len(list(frames_list))

        # Count completed frames (JobCompletedTasks est un tableau d'entiers)
        job_completed = 0
        if completed_list and hasattr(completed_list, "__iter__"):
            job_completed = len(list(completed_list))

        total_frames += job_frames
        total_completed += job_completed

        # Check status
        if job.JobStatus == "Failed":
            any_failed = True
        if job_completed < job_frames:
            all_completed = False

    # FILESYSTEM VERIFICATION FALLBACK
    # Si les jobs sont "Completed" mais qu'on a 0 completed frames, vérifier le disque
    if (
        total_completed == 0
        and total_frames > 0
        and all([job.JobStatus == "Completed" for job in jobs])
    ):
        addLog(
            f"  Jobs marked as Completed but 0/{total_frames} frames reported, checking filesystem..."
        )

        # Reset totals - on va utiliser les chiffres du filesystem
        total_frames = 0
        total_completed = 0

        for job in jobs:
            # Extraire le répertoire de sortie
            output_dirs = job.JobOutputDirectories
            if output_dirs and len(output_dirs) > 0:
                output_dir = output_dirs[0]
                addLog(f"  Checking directory: {output_dir}")

                # Utiliser detect_image_sequence_info pour scanner le disque
                seq_info = detect_image_sequence_info(output_dir)

                if seq_info and seq_info.get("total_frames", 0) > 0:
                    frames_on_disk = seq_info["total_frames"]
                    total_frames += frames_on_disk
                    total_completed += frames_on_disk
                    addLog(
                        f"  Filesystem verification: Found {frames_on_disk} frames on disk"
                    )
                else:
                    addLog(
                        f"  Filesystem verification: No frames found in {output_dir}"
                    )

    # Calculate percentage
    completion_pct = 0
    if total_frames > 0:
        completion_pct = int((total_completed * 100.0) / total_frames)
        addLog(
            f"  Final completion: {total_completed}/{total_frames} frames = {completion_pct}%"
        )

    # Determine status
    status = "Completed" if all_completed else "Active"
    if any_failed:
        status = "Failed"

    return {
        "status": status,
        "completion": completion_pct,
        "completed_frames": total_completed,
        "total_frames": total_frames,
    }


# ============================================================================
# SECTION 3: IMAGE SEQUENCE DETECTION
# ============================================================================


def detect_image_sequence_info(directory):
    """
    Détecte les informations d'une séquence d'images (pattern, first/last frame, total).
    Cherche d'abord directement dans le dossier, puis dans les sous-dossiers.

    Args:
        directory (str): Dossier contenant la séquence

    Returns:
        dict: {
            'pattern': str,
            'first_frame': int,
            'last_frame': int,
            'total_frames': int,
            'subfolder': str (optional)
        } ou None si aucune séquence détectée
    """
    if not os.path.isdir(directory):
        return None

    # Pattern pour détecter les numéros de frame (ex: beauty.0001.exr)
    frame_pattern = re.compile(r"(.+?)\.(\d{4,})\.exr$", re.IGNORECASE)

    def find_sequences_in_folder(folder_path):
        """Helper: cherche les séquences .exr dans un dossier donné."""
        try:
            files = os.listdir(folder_path)
        except (OSError, IOError):
            return {}

        exr_files = [f for f in files if f.lower().endswith(".exr")]

        sequences = {}
        for filename in exr_files:
            match = frame_pattern.match(filename)
            if match:
                base_name = match.group(1)
                frame_num = int(match.group(2))
                padding_len = len(match.group(2))

                if base_name not in sequences:
                    sequences[base_name] = {"frames": [], "padding": padding_len}
                sequences[base_name]["frames"].append(frame_num)

        return sequences

    # Étape 1: Chercher directement dans le dossier version
    sequences = find_sequences_in_folder(directory)
    subfolder_name = None

    # Étape 2: Si rien trouvé, chercher dans les sous-dossiers
    if not sequences:
        try:
            items = os.listdir(directory)
            subdirs = [d for d in items if os.path.isdir(os.path.join(directory, d))]

            # Cherche dans chaque sous-dossier
            all_subfolder_sequences = {}
            for subdir in subdirs:
                subdir_path = os.path.join(directory, subdir)
                subdir_sequences = find_sequences_in_folder(subdir_path)

                if subdir_sequences:
                    # Trouve la séquence avec le plus de frames dans ce sous-dossier
                    main_seq = max(
                        subdir_sequences.items(), key=lambda x: len(x[1]["frames"])
                    )
                    frame_count = len(main_seq[1]["frames"])
                    all_subfolder_sequences[subdir] = {
                        "sequences": subdir_sequences,
                        "main_sequence": main_seq,
                        "frame_count": frame_count,
                    }

            # Prend le sous-dossier avec le plus de frames
            if all_subfolder_sequences:
                best_subfolder = max(
                    all_subfolder_sequences.items(), key=lambda x: x[1]["frame_count"]
                )
                subfolder_name = best_subfolder[0]
                sequences = best_subfolder[1]["sequences"]

        except (OSError, IOError):
            pass

    # Si toujours rien trouvé, retourne None
    if not sequences:
        return None

    # Trouve la séquence avec le plus de frames
    main_sequence = max(sequences.items(), key=lambda x: len(x[1]["frames"]))
    base_name, seq_info = main_sequence

    frames = sorted(seq_info["frames"])
    padding = "#" * seq_info["padding"]

    result = {
        "pattern": f"{base_name}.{padding}.exr",
        "first_frame": frames[0],
        "last_frame": frames[-1],
        "total_frames": len(frames),
    }

    if subfolder_name:
        result["subfolder"] = subfolder_name

    return result


# ============================================================================
# SECTION 4: PRISM STRUCTURE
# ============================================================================


def extract_prism_from_filesystem_path(output_dir):
    """
    Extrait les informations Prism depuis un CHEMIN COMPLET de filesystem.
    UTILISER EN PRIORITÉ car rapide et fiable (1 seul pattern regex).

    Use case: Quand vous avez un path de dossier de rendu existant.

    Args:
        output_dir (str): Chemin complet (ex: "I:/PROJECT/03_Production/Shots/CAPS02/SH0230/Renders/...")

    Returns:
        dict: {
            'drive': str,              # Ex: "I:"
            'project_root': str,       # Ex: "I:/PROJECT"
            'project': str,            # Ex: "PROJECT"
            'sequence': str,           # Ex: "CAPS02"
            'shot': str,               # Ex: "SH0230"
            'shot_path': str          # Ex: "I:/PROJECT/03_Production/Shots/CAPS02/SH0230"
        } ou None si structure non reconnue

    Example:
        >>> extract_prism_from_filesystem_path("I:/MyProject/03_Production/Shots/SEQ01/SH0010/Renders/beauty")
        {'project': 'MyProject', 'sequence': 'SEQ01', 'shot': 'SH0010', ...}
    """
    normalized = output_dir.replace("\\", "/")

    # Pattern Prism: I:/PROJECT/03_Production/Shots/SEQUENCE/SHOT/...
    match = re.search(
        r"([A-Z]:)/([^/]+)/03_Production/Shots/([^/]+)/([^/]+)",
        normalized,
        re.IGNORECASE,
    )

    if match:
        drive = match.group(1)
        project = match.group(2)
        sequence = match.group(3)
        shot = match.group(4)

        project_root = f"{drive}/{project}"
        shot_path = f"{project_root}/03_Production/Shots/{sequence}/{shot}"

        return {
            "drive": drive,
            "project_root": project_root,
            "project": project,
            "sequence": sequence,
            "shot": shot,
            "shot_path": shot_path,
        }

    return None


def extract_project_name(project_root):
    """
    Extrait le nom du projet depuis project_root.

    Args:
        project_root (str): Chemin racine du projet (ex: I:/PROJECT)

    Returns:
        str: Nom du projet ou 'Unknown'
    """
    if not project_root:
        return "Unknown"

    # Prend le dernier segment du path
    normalized = project_root.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]

    return parts[-1] if parts else "Unknown"


def detect_department(shot_path):
    """
    Détecte le nom du département de compositing (Comp, Compo, 2D, etc.).

    Args:
        shot_path (str): Chemin du shot dans Prism

    Returns:
        str: Nom du département trouvé ou 'Compo' par défaut
    """
    if not os.path.isdir(shot_path):
        return "Compo"

    # Variantes possibles du dossier de comp
    variants = ["Compo", "Comp", "2D", "Compositing"]

    for variant in variants:
        test_path = os.path.join(shot_path, variant)
        if os.path.isdir(test_path):
            return variant

    # Par défaut
    return "Compo"


def scan_prism_render_layers(project_root, sequence, shot):
    """
    Scanne l'arborescence Prism 3dRender pour trouver tous les render layers disponibles.

    Args:
        project_root (str): Racine du projet
        sequence (str): Nom de la séquence
        shot (str): Nom du shot

    Returns:
        list: Liste de dicts avec infos sur chaque layer trouvé
    """
    render_base = (
        f"{project_root}/03_Production/Shots/{sequence}/{shot}/Renders/3dRender"
    )

    addLog(f"    scan_prism_render_layers: Checking path: {render_base}")

    if not os.path.isdir(render_base):
        addLog(f"    scan_prism_render_layers: Directory NOT FOUND: {render_base}")
        return []

    addLog(f"    scan_prism_render_layers: Directory exists, listing contents...")

    layers = []

    # Parcourt les dossiers de layers
    try:
        layer_folders = os.listdir(render_base)
        addLog(
            f"    scan_prism_render_layers: Found {len(layer_folders)} items in {render_base}"
        )
    except Exception as e:
        addLog(f"    scan_prism_render_layers: ERROR listing directory: {str(e)}")
        return []

    for layer_name in layer_folders:
        layer_path = os.path.join(render_base, layer_name)

        if not os.path.isdir(layer_path):
            addLog(f"      Skipping '{layer_name}' (not a directory)")
            continue

        addLog(f"      Processing layer: {layer_name}")

        # Cherche les versions
        version_folders_list = os.listdir(layer_path)
        addLog(
            f"        Found {len(version_folders_list)} version folders in {layer_name}"
        )

        for version_folder in version_folders_list:
            version_path = os.path.join(layer_path, version_folder)

            if not os.path.isdir(version_path):
                continue

            # Extrait le numéro de version (accepte v1, v01, v001, v0001, etc.)
            version_match = re.match(r"v(\d+)", version_folder)
            if not version_match:
                addLog(
                    f"          Skipping '{version_folder}' (version pattern not matched)"
                )
                continue

            version_num = int(version_match.group(1))
            addLog(
                f"          Found version: v{version_num:03d} in folder '{version_folder}'"
            )

            # Détecte la séquence d'images
            seq_info = detect_image_sequence_info(version_path)

            if seq_info:
                # Si la séquence est dans un sous-dossier, utilise le chemin complet
                actual_directory = version_path
                if "subfolder" in seq_info:
                    actual_directory = os.path.join(version_path, seq_info["subfolder"])
                    addLog(
                        f"          Images found in subfolder: {seq_info['subfolder']}"
                    )

                layers.append(
                    {
                        "layer_name": layer_name,
                        "version": version_num,
                        "directory": normalize_path_for_nuke(actual_directory),
                        "pattern": seq_info["pattern"],
                        "first_frame": seq_info["first_frame"],
                        "last_frame": seq_info["last_frame"],
                        "total_frames": seq_info["total_frames"],
                        "completion": 100,  # Assume 100% pour scans filesystem
                        "project": extract_project_name(project_root),
                        "sequence": sequence,
                        "shot": shot,
                    }
                )
                addLog(
                    f"          Added: {layer_name} v{version_num:03d} ({seq_info['total_frames']} frames)"
                )
            else:
                addLog(
                    f"          Skipping v{version_num:03d} (no image sequence found)"
                )

    addLog(f"    scan_prism_render_layers: Total layers found: {len(layers)}")
    return layers


def build_prism_slapcomp_paths(
    shot_path, project, sequence, shot, department, version_number
):
    """
    Construit les chemins Prism pour le slap comp.

    Args:
        shot_path (str): Chemin du shot
        project (str): Nom du projet (utilisé pour job_name seulement)
        sequence (str): Nom de la séquence
        shot (str): Nom du shot
        department (str): Nom du département
        version_number (int): Numéro de version

    Returns:
        dict: {
            'scenefile_dir': str,
            'scenefile_path': str,  # Full path to .nk file
            'render_dir': str,      # Includes version subfolder
            'render_filename': str, # Includes version (sans project)
            'job_name': str         # Includes project pour Deadline
        }
    """
    version_str = f"v{version_number:03d}"

    # Nom de fichier SANS project (pour .nk et renders)
    base_name = f"{sequence}_{shot}_SlapComp_{version_str}"

    # Job name AVEC project (pour Deadline seulement)
    job_name = f"{project}_{sequence}_{shot}_SlapComp_{version_str}"

    # Scenefile paths
    scenefile_dir = f"{shot_path}/Scenefiles/{department}/SlapComp"
    scenefile_path = f"{scenefile_dir}/{base_name}.nk"

    # Render paths - includes version subfolder
    render_dir = f"{shot_path}/Renders/2dRender/SlapComp/{version_str}"
    render_filename = f"{base_name}.%04d.exr"

    return {
        "scenefile_dir": normalize_path_for_nuke(scenefile_dir),
        "scenefile_path": normalize_path_for_nuke(scenefile_path),
        "render_dir": normalize_path_for_nuke(render_dir),
        "render_filename": render_filename,
        "job_name": job_name,
    }


def extract_prism_from_job_name(job):
    """
    Extrait les informations Prism depuis les MÉTADONNÉES d'un job Deadline (JobName/BatchName).
    UTILISER EN FALLBACK si extract_prism_from_filesystem_path() échoue.

    Use case: Quand le path n'existe pas ou ne suit pas la structure Prism exacte.

    Plus robuste (7 patterns) mais plus lent et peut créer faux positifs.
    Utilise des patterns GÉNÉRIQUES qui ne dépendent pas de noms de séquences spécifiques.

    Args:
        job: Job Deadline avec JobName et JobBatchName

    Returns:
        dict or None: {
            'project_root': str,       # Ex: "I:/PROJECT"
            'project': str,            # Ex: "PROJECT"
            'sequence': str,           # Ex: "CAPS02"
            'shot': str,               # Ex: "SH0230"
            'shot_path': str          # Ex: "I:/PROJECT/03_Production/Shots/CAPS02/SH0230"
        } ou None si impossible d'extraire

    Example:
        >>> job.JobName = "PROJECT_CAPS02-SH0230_BG_v001_render"
        >>> extract_prism_from_job_name(job)
        {'project': 'PROJECT', 'sequence': 'CAPS02', 'shot': 'SH0230', ...}
    """
    # Patterns pour extraire sequence/shot (ordre de priorité)
    seq_shot_patterns = [
        # 1. Format standard: LETTRES##-LETTRES## ou LETTRES##_LETTRES##
        (r"([A-Z]+\d+)[-_]([A-Z]+\d+)", "direct_match"),
        # 2. Dans un chemin /Shots/SEQ/SHOT/
        (r"/Shots/([^/]+)/([^/]+)/", "path_based"),
        # 3. Entre underscores: _SEQ##-SHOT##_
        (r"_([A-Z]+\d+)[-_]([A-Z]+\d+)_", "mid_string"),
        # 4. N'importe où dans la chaîne (plus permissif)
        (r"([A-Z]{1,10}\d+)[-_]([A-Z]{1,10}\d+)", "anywhere"),
    ]

    # Essayer d'extraire depuis le job name
    job_name = job.JobName

    sequence = None
    shot = None
    project = None

    for pattern, pattern_type in seq_shot_patterns:
        match = re.search(pattern, job_name, re.IGNORECASE)
        if match:
            sequence = match.group(1).upper()
            shot = match.group(2).upper()
            addLog(
                f"  Extracted sequence/shot from job name ({pattern_type}): {sequence}/{shot}"
            )
            break

    # Si échec, essayer le batch name
    if not sequence or not shot:
        batch_name = job.JobBatchName
        if batch_name:
            for pattern, pattern_type in seq_shot_patterns:
                match = re.search(pattern, batch_name, re.IGNORECASE)
                if match:
                    sequence = match.group(1).upper()
                    shot = match.group(2).upper()
                    addLog(
                        f"  Extracted sequence/shot from batch name ({pattern_type}): {sequence}/{shot}"
                    )
                    break

    if not sequence or not shot:
        return None

    # Extraire le nom du projet (tout ce qui est avant la sequence)
    # Pattern: cherche PROJECT_SEQ ou PROJECT/SEQ
    project_patterns = [
        # 1. Underscore separator: PROJECT_SEQ##
        rf"(.+?)_+{re.escape(sequence)}",
        # 2. Slash separator: PROJECT/SEQ##
        rf"(.+?)/+{re.escape(sequence)}",
        # 3. Direct prefix sans séparateur (rare)
        rf"([A-Z][a-z0-9_]+){re.escape(sequence)}",
    ]

    for pattern in project_patterns:
        match = re.search(pattern, job_name, re.IGNORECASE)
        if match:
            project = match.group(1).strip("_/\\")
            # Nettoie le nom du projet (enlève séparateurs multiples, etc.)
            project = re.sub(r"[_/\\]+$", "", project)
            addLog(f"  Extracted project from job name: {project}")
            break

    # Si pas de projet trouvé, essayer batch name
    if not project:
        batch_name = job.JobBatchName
        if batch_name:
            for pattern in project_patterns:
                match = re.search(pattern, batch_name, re.IGNORECASE)
                if match:
                    project = match.group(1).strip("_/\\")
                    project = re.sub(r"[_/\\]+$", "", project)
                    addLog(f"  Extracted project from batch name: {project}")
                    break

    # Si toujours pas de projet, utiliser un nom par défaut
    if not project:
        project = "UnknownProject"
        addLog(f"  Could not extract project name, using default: {project}")

    # Construire les paths Prism (assume I:/ par défaut)
    project_root = f"I:/{project}"
    shot_path = f"{project_root}/03_Production/Shots/{sequence}/{shot}"

    return {
        "project_root": project_root,
        "project": project,
        "sequence": sequence,
        "shot": shot,
        "shot_path": shot_path,
    }


def get_prism_info_smart(job, output_dirs=None):
    """
    Extrait intelligemment les infos Prism en essayant plusieurs stratégies.

    Stratégie (ordre de priorité):
    1. Depuis filesystem path (rapide, fiable) si output_dirs fourni
    2. Depuis job metadata (fallback robuste)

    Args:
        job: Job Deadline
        output_dirs (list, optional): Liste de directories de sortie

    Returns:
        dict: Informations Prism ou None si extraction impossible

    Example:
        >>> prism_info = get_prism_info_smart(job, output_dirs=["/path/to/renders"])
    """
    prism_info = None

    # Stratégie 1: Essayer filesystem path (simple et rapide)
    if output_dirs and len(output_dirs) > 0:
        prism_info = extract_prism_from_filesystem_path(output_dirs[0])
        if prism_info:
            addLog("  Prism info extracted from filesystem path")
            return prism_info

    # Stratégie 2: Fallback sur job metadata (robuste mais plus lent)
    prism_info = extract_prism_from_job_name(job)
    if prism_info:
        addLog("  Prism info extracted from job metadata (fallback)")

    return prism_info


def find_next_slapcomp_version(scenefile_dir, render_filename):
    """
    Trouve le prochain numéro de version disponible pour un slap comp.

    Args:
        scenefile_dir (str): Dossier des scenefiles
        render_filename (str): Base du nom de fichier

    Returns:
        int: Prochain numéro de version (ex: 1, 2, 3...)
    """
    addLog(f"\n=== find_next_slapcomp_version: START ===")
    addLog(f"Scenefile dir: {scenefile_dir}")
    addLog(f"Render filename base: {render_filename}")

    if not os.path.isdir(scenefile_dir):
        addLog(f"Directory does not exist, returning version 1")
        return 1

    existing_files = os.listdir(scenefile_dir)
    addLog(f"Found {len(existing_files)} files in directory")

    max_version = 0
    pattern = re.compile(rf"{re.escape(render_filename)}_v(\d{{3,4}})\.nk$")
    addLog(f"Pattern to match: {pattern.pattern}")

    for filename in existing_files:
        match = pattern.search(
            filename
        )  # Changed from .match() to .search() for robustness
        if match:
            version = int(match.group(1))
            addLog(f"  Matched file: {filename} -> version {version}")
            max_version = max(max_version, version)
        else:
            addLog(f"  Skipped file: {filename} (no match)")

    next_version = max_version + 1
    addLog(f"Max version found: {max_version}, returning next version: {next_version}")
    addLog(f"=== find_next_slapcomp_version: END ===\n")

    return next_version


# ============================================================================
# SECTION 5: OUTPUT COLLECTION
# ============================================================================


def get_output_dirs(jobs_to_process, filter_qc_layers=True):
    """
    Extrait les dossiers de sortie des jobs et fusionne avec les render layers du filesystem.
    Scan SYSTÉMATIQUE du filesystem même si aucun job Deadline valide n'est trouvé.

    Args:
        jobs_to_process (list): Liste de jobs Deadline
        filter_qc_layers (bool): Si True, filtre les layers commençant par "QC"

    Returns:
        list: Liste de dicts avec toutes les infos de sortie (versions multiples, completion, etc.)
    """
    addLog("\n=== get_output_dirs: START ===")
    addLog(f"Jobs to process: {len(jobs_to_process)}")

    for idx, job in enumerate(jobs_to_process):
        addLog(f"  Job {idx + 1}: {job.JobName}")

    output_info = []

    # Groupe les jobs par clé (sans suffixe _high_prio_render ou _render)
    addLog("\nAppel de group_high_prio_and_render_jobs...")
    grouped_jobs = group_high_prio_and_render_jobs(jobs_to_process)
    addLog(f"Retour de group_high_prio_and_render_jobs: {type(grouped_jobs)}")

    addLog(f"Jobs groupés: {len(grouped_jobs)} groupes (toutes versions)")

    # Log détaillé des groupes pour debug
    for (base_name, version), jobs in grouped_jobs.items():
        addLog(f"  Groupe: base='{base_name}' v{version:03d} ({len(jobs)} job(s))")

    # ============================================================================
    # PASSE 1: Collecter TOUS les contextes Prism (project/sequence/shot)
    # ============================================================================
    prism_contexts = {}  # Dict: {(project_root, sequence, shot): prism_info_dict}

    addLog("\n--- PASSE 1: Collecte des contextes Prism ---")

    for (base_name, version), associated_jobs in grouped_jobs.items():
        job = associated_jobs[0]

        output_dirs = job.JobOutputDirectories

        # Extraction intelligente Prism (path → metadata fallback)
        prism_info = get_prism_info_smart(job, output_dirs)

        if prism_info:
            context_key = (
                prism_info["project_root"],
                prism_info["sequence"],
                prism_info["shot"],
            )
            prism_contexts[context_key] = prism_info
            addLog(
                f"  Contexte ajouté: {prism_info['project']}/{prism_info['sequence']}/{prism_info['shot']}"
            )

    addLog(f"Total contextes Prism: {len(prism_contexts)}")

    # ============================================================================
    # PASSE 2: Traiter les jobs Deadline et extraire infos
    # ============================================================================
    addLog("\n--- PASSE 2: Traitement jobs Deadline ---")

    for (base_name, version), associated_jobs in grouped_jobs.items():
        job = associated_jobs[0]

        addLog(f"Associated jobs : {associated_jobs}")
        addLog(f"First Job: {job.JobName}")

        output_dirs = job.JobOutputDirectories

        if not output_dirs or len(output_dirs) == 0:
            addLog(f"  Skip job (no output_dir): {job.JobName}")
            continue

        output_dir = output_dirs[0]

        # Extrait le nom du layer depuis base_name avec PATTERNS GÉNÉRIQUES
        layer_name = os.path.basename(output_dir)  # Fallback par défaut

        # PATTERNS GÉNÉRIQUES pour extraire layer name (pas de "CAPS" en dur!)
        layer_patterns = [
            # 1. Format complet: PROJECT_SEQ##-SHOT##_LAYER
            (r"(.+?)_([A-Z]+\d+)[-_]([A-Z]+\d+)_(.+)", 4),
            # 2. Format court: SEQ##-SHOT##_LAYER
            (r"^([A-Z]+\d+)[-_]([A-Z]+\d+)_(.+)", 3),
            # 3. Format avec underscores: PROJECT_SEQ##_SHOT##_LAYER
            (r"(.+?)_([A-Z]+\d+)_([A-Z]+\d+)_(.+)", 4),
            # 4. Dernier segment après underscore: ...SHOT##_LAYER
            (r"_([^_]+)$", 1),
        ]

        for pattern, group_idx in layer_patterns:
            shot_match = re.search(pattern, base_name)
            if shot_match:
                layer_name = shot_match.group(group_idx)
                addLog(
                    f"  Layer extracted via pattern: '{layer_name}' from base: '{base_name}' (pattern #{layer_patterns.index((pattern, group_idx)) + 1})"
                )
                break
        else:
            # Fallback: utilise basename de output_dir
            layer_name = os.path.basename(output_dir)
            addLog(
                f"  Layer extracted via fallback (basename): '{layer_name}' from base: '{base_name}'"
            )

        # Détecte la séquence d'images
        seq_info = detect_image_sequence_info(output_dir)

        if not seq_info:
            addLog(f"  Skip job (no sequence): {output_dir}")
            continue

        # Si la séquence est dans un sous-dossier, utilise le chemin complet
        actual_directory = output_dir
        if "subfolder" in seq_info:
            actual_directory = os.path.join(output_dir, seq_info["subfolder"])
            addLog(f"  Images found in subfolder: {seq_info['subfolder']}")

        # Calcule frame range et completion combinés
        first_frame, last_frame = get_combined_frame_range(associated_jobs)
        completion_info = get_combined_job_completion(associated_jobs)

        # Parse Prism path
        prism_info = extract_prism_from_filesystem_path(output_dir)

        info = {
            "directory": normalize_path_for_nuke(actual_directory),
            "pattern": seq_info["pattern"],
            "first_frame": first_frame,
            "last_frame": last_frame,
            "total_frames": completion_info["total_frames"],
            "layer_name": layer_name,
            "version": version,
            "completion": completion_info["completion"],
            "status": completion_info["status"],
            "source": "deadline",
            "job_ids": [j.JobId for j in associated_jobs],
            "merge_operation": "over",  # Default
        }

        # Ajoute infos Prism si disponibles
        if prism_info:
            info.update(
                {
                    "project": prism_info["project"],
                    "sequence": prism_info["sequence"],
                    "shot": prism_info["shot"],
                    "shot_path": prism_info["shot_path"],
                    "project_root": prism_info["project_root"],
                }
            )

        output_info.append(info)
        addLog(
            f"  Added from Deadline: {layer_name} v{version:03d} ({completion_info['completion']}%)"
        )

    addLog(f"Layers depuis Deadline: {len(output_info)}")

    # ============================================================================
    # PASSE 3: Scanner filesystem pour TOUS les contextes Prism
    # ============================================================================
    addLog("\n--- PASSE 3: Scan filesystem ---")

    filesystem_count = 0

    for context_key, prism_info in prism_contexts.items():
        project_root, sequence, shot = context_key
        addLog(f"  Scanning: {project_root}/{sequence}/{shot}")
        filesystem_layers = scan_prism_render_layers(project_root, sequence, shot)

        for fs_layer in filesystem_layers:
            # Vérifie si cette version existe déjà dans output_info
            already_exists = False
            for existing in output_info:
                if (
                    existing.get("layer_name") == fs_layer["layer_name"]
                    and existing.get("version") == fs_layer["version"]
                    and existing.get("sequence") == sequence
                    and existing.get("shot") == shot
                ):
                    already_exists = True
                    break

            if not already_exists:
                fs_layer["source"] = "filesystem"
                fs_layer["status"] = "Completed"
                fs_layer["merge_operation"] = "over"
                fs_layer["shot_path"] = prism_info["shot_path"]
                fs_layer["project_root"] = prism_info["project_root"]
                output_info.append(fs_layer)
                filesystem_count += 1
                addLog(
                    f"    Added from filesystem: {fs_layer['layer_name']} v{fs_layer['version']:03d}"
                )

    addLog(f"Layers depuis filesystem: {filesystem_count}")

    # Filtre les layers QC si demandé
    if filter_qc_layers:
        before_filter = len(output_info)
        output_info = [
            info
            for info in output_info
            if not info["layer_name"].upper().startswith("QC")
        ]
        addLog(f"\nFiltre QC: {before_filter - len(output_info)} layers retirés")

    addLog(f"\n=== get_output_dirs: END - Total: {len(output_info)} layers ===\n")

    return output_info


def group_output_info_for_ui(output_info):
    """
    Regroupe les entrées output_info par layer_name pour l'affichage dans l'UI.
    Chaque layer aura toutes ses versions dans un tableau 'versions'.

    Args:
        output_info (list): Liste de dicts avec une entrée par version
            Format: [{'layer_name': 'X', 'version': 1, 'completion': 50, ...}, ...]

    Returns:
        list: Liste de dicts groupés par layer
            Format: [{
                'layer_name': 'X',
                'source': 'deadline',  # 'deadline' si au moins une version vient de deadline
                'versions': [
                    {
                        'version': 'v001',
                        'completion_percent': 50,
                        'status': 'Active',
                        'frames_completed': 50,
                        'frames_total': 100,
                        'directory': '...',
                        'pattern': '...',
                        'first_frame': 1,
                        'last_frame': 100
                    },
                    ...
                ],
                'selected_version_index': 0,  # Index de la dernière version
                'merge_operation': 'over',
                'project': '...',
                'sequence': '...',
                'shot': '...'
            }, ...]
    """
    addLog("\n=== group_output_info_for_ui: START ===")

    # Groupe par layer_name
    layers_dict = {}  # {layer_name: [list of version entries]}

    for entry in output_info:
        layer_name = entry.get("layer_name", "Unknown")

        if layer_name not in layers_dict:
            layers_dict[layer_name] = []

        layers_dict[layer_name].append(entry)

    addLog(f"Found {len(layers_dict)} unique layers")

    # Construit la structure pour l'UI
    grouped_output = []

    for layer_name, entries in layers_dict.items():
        # Trie les entrées par numéro de version
        entries_sorted = sorted(entries, key=lambda x: x.get("version", 0))

        # Détermine la source prioritaire (deadline > filesystem)
        has_deadline = any(e.get("source") == "deadline" for e in entries_sorted)
        source = "deadline" if has_deadline else "filesystem"

        # Construit le tableau de versions
        versions_list = []
        for entry in entries_sorted:
            version_num = entry.get("version", 0)
            version_str = f"v{version_num:03d}"

            # Extrait les infos de complétion
            completion = entry.get("completion", 100)
            status = entry.get("status", "Completed")
            total_frames = entry.get("total_frames", 0)

            # Calcule frames_completed depuis completion
            frames_completed = (
                int((completion * total_frames) / 100.0) if total_frames > 0 else 0
            )

            version_info = {
                "version": version_str,
                "completion_percent": completion,
                "status": status,
                "frames_completed": frames_completed,
                "frames_total": total_frames,
                "directory": entry.get("directory", ""),
                "pattern": entry.get("pattern", ""),
                "first_frame": entry.get("first_frame", 1),
                "last_frame": entry.get("last_frame", 1),
                "source": entry.get("source", "filesystem"),
                "job_id": entry.get("job_id"),
                "job_ids": entry.get("job_ids", []),
            }

            versions_list.append(version_info)

        # Prend les métadonnées de la dernière version
        last_entry = entries_sorted[-1]

        grouped_entry = {
            "layer_name": layer_name,
            "source": source,
            "versions": versions_list,
            "selected_version_index": len(versions_list)
            - 1,  # Dernière version par défaut
            "merge_operation": last_entry.get("merge_operation", "over"),
            "project": last_entry.get("project", ""),
            "sequence": last_entry.get("sequence", ""),
            "shot": last_entry.get("shot", ""),
            "shot_path": last_entry.get("shot_path", ""),
            "project_root": last_entry.get("project_root", ""),
        }

        grouped_output.append(grouped_entry)

        addLog(
            f"  Layer '{layer_name}': {len(versions_list)} version(s), source={source}"
        )

    addLog(f"=== group_output_info_for_ui: END - {len(grouped_output)} layers ===\n")

    return grouped_output


# ============================================================================
# SECTION 6: NUKE EXECUTION
# ============================================================================


def render_nuke_script(nuke_script_path, first_frame, last_frame):
    """
    Lance le rendu du script Nuke en ligne de commande (rendu local).

    Args:
        nuke_script_path (str): Chemin du script Nuke (.nk)
        first_frame (int): Première frame
        last_frame (int): Dernière frame
    """
    nuke_exe = get_nuke_executable()

    cmd = [
        nuke_exe,
        "-x",  # Mode batch
        nuke_script_path,
        f"{first_frame}-{last_frame}",
    ]

    addLog("\nLancement rendu Nuke:")
    addLog(f"  Commande: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        # Log la sortie en temps réel
        for line in iter(process.stdout.readline, ""):
            if line:
                addLog(line.rstrip())

        process.wait()

        if process.returncode == 0:
            addLog("\n=== Rendu terminé avec succès ===")
        else:
            addLog(f"\n=== Erreur rendu (code: {process.returncode}) ===")

    except Exception as e:
        addLog(f"Erreur lancement rendu: {str(e)}")


def submit_to_deadline(
    nuke_script_path,
    first_frame,
    last_frame,
    output_info,
    render_dir,
    render_filename,
    job_name=None,
):
    """
    Soumet le slap comp à Deadline avec dépendances sur les jobs sources.

    Args:
        nuke_script_path (str): Chemin du script Nuke
        first_frame (int): Première frame
        last_frame (int): Dernière frame
        output_info (list): Liste des infos de sortie (pour dépendances)
        render_dir (str): Dossier de rendu
        render_filename (str): Nom du fichier de rendu
        job_name (str): Nom du job Deadline (optionnel, extrait du .nk si non fourni)
    """
    # Importe le module de soumission
    repo_path = RepositoryUtils.GetRootDirectory()
    submission_path = os.path.join(
        repo_path, "custom", "scripts", "Submission", "SlapComp"
    )
    if submission_path not in sys.path:
        sys.path.insert(0, submission_path)

    try:
        from SubmitSlapCompToDeadline import submit_slap_comp_job

        # Collecte les job IDs pour les dépendances
        dependency_job_ids = []
        for info in output_info:
            if "job_id" in info and info["job_id"] is not None:
                dependency_job_ids.append(info["job_id"])
                addLog(f"single, current deps : {dependency_job_ids}")
            elif "job_ids" in info:
                dependency_job_ids.extend(info["job_ids"])
                addLog(f"multi, current deps : {dependency_job_ids}")
        # Retire les doublons
        dependency_job_ids = list(set(dependency_job_ids))
        addLog(f"Deps without dupes : {dependency_job_ids}")

        addLog("\n=== Soumission à Deadline ===")
        addLog(f"Fichier Nuke: {normalize_path_for_nuke(nuke_script_path)}")
        addLog(f"Frame range: {first_frame}-{last_frame}")
        addLog(f"Dépendances: {len(dependency_job_ids)} job(s)")
        for jid in dependency_job_ids:
            addLog(f"  - {jid}")

        if render_dir and render_filename:
            addLog(f"Render dir: {normalize_path_for_nuke(render_dir)}")
            addLog(f"Render filename: {render_filename}")

        # Soumet le job via le module externe
        job_id = submit_slap_comp_job(
            nk_path=nuke_script_path,
            first_frame=first_frame,
            last_frame=last_frame,
            dependency_job_ids=dependency_job_ids,
            render_dir=render_dir,
            render_filename=render_filename,
            job_name=job_name,
            group="nuke_grp",
        )

        if job_id:
            addLog("\n=== SUCCESS ===")
            addLog(f"Job soumis: {job_id}")
        else:
            addLog("\n=== ERREUR ===")
            addLog("Échec de la soumission")

    except Exception as e:
        addLog(f"ERREUR: {str(e)}")
        import traceback

        traceback.print_exc()


def call_nuke_script(output_info, render_mode="none"):
    """
    Génère et exécute le script Nuke pour créer le slap comp.

    Args:
        output_info (list): Liste ordonnée des infos de sortie
        render_mode (str): "none", "local", ou "deadline"
    """

    addLog(f"Full output info : {output_info}")

    if not output_info or len(output_info) == 0:
        addLog("Aucune donnée à traiter")
        return

    # Extrait infos du premier item
    first_info = output_info[0]
    first_directory = first_info.get("directory", "")

    # Extrait les métadonnées de base (peuvent déjà être présentes)
    project = first_info.get("project", "Unknown")
    sequence = first_info.get("sequence", "Unknown")
    shot = first_info.get("shot", "Unknown")

    # Parse le directory pour obtenir prism_info complet (comme ancienne version)
    prism_info = extract_prism_from_filesystem_path(first_directory)

    # Construit les paths Prism SI prism_info valide
    if prism_info:
        # Utilise les données extraites de prism_info
        shot_path = prism_info["shot_path"]
        project = prism_info.get(
            "project", project
        )  # Override si trouvé dans prism_info
        sequence = prism_info["sequence"]
        shot = prism_info["shot"]

        # Détecte le département
        department = detect_department(shot_path)

        # STEP 1: Build temp paths avec version=1 pour trouver scenefile_dir
        temp_paths = build_prism_slapcomp_paths(
            shot_path, project, sequence, shot, department, 1
        )
        scenefile_dir = temp_paths["scenefile_dir"]

        # STEP 2: Trouve la prochaine version (sans project dans le nom de fichier)
        render_filename_base = f"{sequence}_{shot}_SlapComp"
        next_version = find_next_slapcomp_version(scenefile_dir, render_filename_base)

        # STEP 3: Build final paths avec la vraie version
        paths = build_prism_slapcomp_paths(
            shot_path, project, sequence, shot, department, next_version
        )

        output_nk = paths["scenefile_path"]
        render_dir = paths["render_dir"]
        render_filename = paths["render_filename"]
        job_name = paths["job_name"]

        addLog("\n=== Structure Prism détectée ===")
        addLog(f"Projet: {project}")
        addLog(f"Séquence: {sequence}")
        addLog(f"Shot: {shot}")
        addLog(f"Département: {department}")
        addLog(f"Version: v{next_version:03d}")
        addLog(f"Job name: {job_name}")
    else:
        # Fallback si pas de structure Prism
        output_dir = first_info.get("directory", "")
        parent_dir = os.path.dirname(output_dir)
        scenefile_dir = parent_dir
        render_dir = parent_dir
        render_filename_base = "slap_comp"

        next_version = find_next_slapcomp_version(scenefile_dir, render_filename_base)
        output_nk = os.path.join(
            scenefile_dir, f"{render_filename_base}_v{next_version:03d}.nk"
        )
        render_filename = f"{render_filename_base}_v{next_version:03d}.%04d.exr"
        job_name = None  # Pas de job name spécifique en fallback

        addLog("\n=== Structure Prism non détectée, utilisation fallback ===")

    addLog("\nGénération slap comp:")
    addLog(f"  Scenefile: {normalize_path_for_nuke(output_nk)}")
    addLog(f"  Render dir: {normalize_path_for_nuke(render_dir)}")
    addLog(f"  Render filename: {render_filename}")

    # Crée les dossiers si nécessaire
    os.makedirs(scenefile_dir, exist_ok=True)
    os.makedirs(render_dir, exist_ok=True)

    # Génère le script Python temporaire pour Nuke
    ocio_config = get_file_path_from_config("OCIO")
    script_content = f"""
import nuke
import os

# Clear existing script
nuke.scriptClear()

# Configure OCIO
root = nuke.toNode("root")
root.knob("colorManagement").setValue("OCIO")
root.knob("OCIO_config").setValue("custom")
root.knob("customOCIOConfigPath").setValue({ocio_config})

read_nodes = []

# Configuration positionnement nodes
x_position = 0
spacing = 200  # Espacement horizontal entre Read nodes

# Create Read nodes
"""

    for idx, info in enumerate(output_info):
        directory = info["directory"]
        pattern = info["pattern"]
        first_frame = info["first_frame"]
        last_frame = info["last_frame"]
        layer_name = info.get("layer_name", f"Layer{idx}")

        full_path = f"{directory}/{pattern}"
        x_pos = idx * 200  # Calcule position X pour ce Read node

        script_content += f"""
# Read node {idx}: {layer_name}
read{idx} = nuke.createNode('Read', inpanel=False)
read{idx}.knob('file').setValue('{full_path}')
read{idx}.knob('first').setValue({first_frame})
read{idx}.knob('last').setValue({last_frame})
read{idx}.knob('origfirst').setValue({first_frame})
read{idx}.knob('origlast').setValue({last_frame})
read{idx}.knob('label').setValue('{layer_name}')
read{idx}.setXYpos({x_pos}, 0)
read_nodes.append(read{idx})

"""

    # Ajoute configuration frame range
    script_content += """
# Configure le frame range du script
if read_nodes:
    all_first = min(int(n.knob('first').value()) for n in read_nodes)
    all_last = max(int(n.knob('last').value()) for n in read_nodes)
    nuke.root().knob('first_frame').setValue(all_first)
    nuke.root().knob('last_frame').setValue(all_last)

"""

    # Ajoute les Merge nodes
    script_content += """
# Create Merge stack avec positionnement
merge_start_y = 150
merge_spacing = 100
merge_x = 0  # Position X fixe pour tous les merges
current_merge_y = merge_start_y

current_node = read_nodes[0]

for i in range(1, len(read_nodes)):
    merge = nuke.createNode('Merge2', inpanel=False)
"""

    # Configure merge operations
    for idx in range(1, len(output_info)):
        merge_op = output_info[idx].get("merge_operation", "over")
        script_content += f"""
    if i == {idx}:
        merge.knob('operation').setValue('{merge_op}')
"""

    script_content += """
    merge.setInput(0, current_node)  # B input (background)
    merge.setInput(1, read_nodes[i])  # A input (foreground)
    merge.setXYpos(merge_x, current_merge_y)
    current_node = merge
    current_merge_y += merge_spacing

# Create Write node
write = nuke.createNode('Write', inpanel=False)
write.knob('file').setValue('{render_path}')
write.knob('file_type').setValue('exr')
write.knob('compression').setValue('DWAB')
write.knob('channels').setValue('rgba')
write.setInput(0, current_node)
write.setXYpos(merge_x, current_merge_y + 50)
write.knob('create_directories').setValue(True)

# Save script
nuke.scriptSaveAs('{output_nk}', overwrite=1)

print("Slap comp created successfully: {output_nk}")
""".format(
        render_path=normalize_path_for_nuke(f"{render_dir}/{render_filename}"),
        output_nk=normalize_path_for_nuke(output_nk),
    )

    # Écrit le script temporaire
    temp_script = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    temp_script.write(script_content)
    temp_script_path = temp_script.name
    temp_script.close()

    addLog(f"\nScript temporaire: {temp_script_path}")

    # Exécute Nuke en mode terminal
    nuke_exe = get_nuke_executable()
    cmd = [nuke_exe, "-t", temp_script_path]

    addLog(f"Commande: {' '.join(cmd)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        # Log output
        for line in iter(process.stdout.readline, ""):
            if line:
                addLog(line.rstrip())

        process.wait()

        # Supprime le script temporaire
        try:
            os.unlink(temp_script_path)
        except:
            pass

        if process.returncode == 0:
            if os.path.exists(output_nk):
                addLog("\n=== SUCCESS ===")
                addLog(f"Slap comp cree: {normalize_path_for_nuke(output_nk)}")

                # Lance le rendu selon le mode choisi
                if render_mode != "none":
                    # Calcule le frame range global
                    all_first = min(info["first_frame"] for info in output_info)
                    all_last = max(info["last_frame"] for info in output_info)

                    if render_mode == "local":
                        render_nuke_script(output_nk, all_first, all_last)
                    elif render_mode == "deadline":
                        submit_to_deadline(
                            output_nk,
                            all_first,
                            all_last,
                            output_info,
                            render_dir,
                            render_filename,
                            job_name,
                        )

                    generate_versioninfo(
                        output_nk, sequence, shot, department, next_version
                    )

            else:
                addLog("\n=== ATTENTION ===")
                addLog(f"Le fichier n'existe pas: {normalize_path_for_nuke(output_nk)}")
        else:
            addLog("\n=== ERREUR ===")
            addLog(f"Code retour: {process.returncode}")

    except Exception as e:
        addLog(f"ERREUR: {str(e)}")


# ============================================================================
# SECTION 7: PRESET MANAGEMENT
# ============================================================================


def get_preset_dir(project):
    """
    Retourne le répertoire des presets pour un projet.

    Args:
        project (str): Nom du projet

    Returns:
        str: Chemin du dossier de presets ou None
    """
    if not project:
        return None
    return f"I:\\{project}\\00_Pipeline\\Presets\\SlapComp"


def load_preset(project, sequence, shot):
    """
    Charge le preset approprié (shot override > project > None).

    Args:
        project (str): Nom du projet
        sequence (str): Nom de la séquence
        shot (str): Nom du shot

    Returns:
        dict or None: Données du preset ou None si aucun preset trouvé
    """
    preset_dir = get_preset_dir(project)

    if not preset_dir or not os.path.exists(preset_dir):
        addLog("Aucun répertoire de presets trouvé")
        return None

    preset_data = None
    preset_source = ""

    # 1. Cherche override shot
    if shot:
        shot_overrides_path = os.path.join(preset_dir, "shot_overrides.json")
        if os.path.exists(shot_overrides_path):
            try:
                with open(shot_overrides_path, "r") as f:
                    overrides = json.load(f)
                    shot_key = f"{sequence}-{shot}" if sequence else shot
                    if shot_key in overrides:
                        preset_data = overrides[shot_key]
                        preset_source = f"Shot override ({shot_key})"
            except Exception as e:
                addLog(f"Erreur lecture shot_overrides.json: {str(e)}")

    # 2. Sinon, cherche preset projet
    if not preset_data:
        project_preset_path = os.path.join(preset_dir, "project_preset.json")
        if os.path.exists(project_preset_path):
            try:
                with open(project_preset_path, "r") as f:
                    preset_data = json.load(f)
                    preset_source = "Project preset"
            except Exception as e:
                addLog(f"Erreur lecture project_preset.json: {str(e)}")

    if preset_data:
        addLog(f"Preset chargé: {preset_source}")
    else:
        addLog("Aucun preset trouvé - utilisation ordre par défaut")

    return preset_data


def apply_preset_data(output_info, preset_data):
    """
    Applique les données du preset à output_info.

    Args:
        output_info (list): Liste des infos de sortie
        preset_data (dict): Données du preset avec 'layer_order' et 'default_merge_ops'

    Returns:
        list: output_info réordonné selon le preset
    """
    if not preset_data:
        return output_info

    layer_order = preset_data.get("layer_order", [])
    default_merge_ops = preset_data.get("default_merge_ops", {})

    if not layer_order:
        return output_info

    # Crée un dictionnaire layer_name -> info
    layers_dict = {info.get("layer_name"): info for info in output_info}

    # Réordonne selon le preset
    reordered = []

    # Ajoute d'abord les layers dans l'ordre du preset
    for layer_name in layer_order:
        if layer_name in layers_dict:
            info = layers_dict[layer_name]
            # Applique le merge operation du preset
            if layer_name in default_merge_ops:
                info["merge_operation"] = default_merge_ops[layer_name]
            reordered.append(info)

    # Ajoute les layers non présents dans le preset à la fin (exclus par défaut)
    for layer_name, info in layers_dict.items():
        if layer_name not in layer_order:
            info["included"] = False
            reordered.append(info)
            addLog(
                f"Layer '{layer_name}' non présent dans preset, ajouté à la fin (non inclus)"
            )

    return reordered


def save_preset_project(project, preset_data):
    """
    Sauvegarde un preset projet.

    Args:
        project (str): Nom du projet
        preset_data (dict): Données du preset

    Returns:
        str: Chemin du fichier sauvegardé ou None en cas d'erreur
    """
    preset_dir = get_preset_dir(project)

    if not preset_dir:
        addLog("Erreur: impossible de déterminer le répertoire de presets")
        return None

    # Crée le dossier si nécessaire
    if not os.path.exists(preset_dir):
        try:
            os.makedirs(preset_dir)
            addLog(f"Dossier créé: {preset_dir}")
        except Exception as e:
            addLog(f"Erreur création dossier: {str(e)}")
            return None

    project_preset_path = os.path.join(preset_dir, "project_preset.json")

    try:
        with open(project_preset_path, "w") as f:
            json.dump(preset_data, f, indent=2)
        addLog(f"Preset projet sauvegardé: {project_preset_path}")
        return project_preset_path
    except Exception as e:
        addLog(f"Erreur sauvegarde preset: {str(e)}")
        return None


def save_preset_shot(project, sequence, shot, preset_data):
    """
    Sauvegarde un preset shot dans shot_overrides.json.

    Args:
        project (str): Nom du projet
        sequence (str): Nom de la séquence
        shot (str): Nom du shot
        preset_data (dict): Données du preset

    Returns:
        str: Clé du shot sauvegardé ou None en cas d'erreur
    """
    preset_dir = get_preset_dir(project)

    if not preset_dir:
        addLog("Erreur: impossible de déterminer le répertoire de presets")
        return None

    # Crée le dossier si nécessaire
    if not os.path.exists(preset_dir):
        try:
            os.makedirs(preset_dir)
            addLog(f"Dossier créé: {preset_dir}")
        except Exception as e:
            addLog(f"Erreur création dossier: {str(e)}")
            return None

    shot_overrides_path = os.path.join(preset_dir, "shot_overrides.json")

    # Charge les overrides existants
    overrides = {}
    if os.path.exists(shot_overrides_path):
        try:
            with open(shot_overrides_path, "r") as f:
                overrides = json.load(f)
        except Exception as e:
            addLog(f"Erreur lecture shot_overrides.json: {str(e)}")

    # Ajoute/update l'override pour ce shot
    shot_key = f"{sequence}-{shot}" if sequence else shot
    overrides[shot_key] = preset_data

    # Sauvegarde
    try:
        with open(shot_overrides_path, "w") as f:
            json.dump(overrides, f, indent=2)
        addLog(f"Preset shot sauvegardé: {shot_key}")
        return shot_key
    except Exception as e:
        addLog(f"Erreur sauvegarde shot override: {str(e)}")
        return None


# ============================================================================
# SECTION 8: AUTOMATION HELPERS
# ============================================================================


def select_latest_complete_versions(output_info):
    """
    Sélectionne automatiquement la dernière version complète (100%) pour chaque layer.

    Args:
        output_info (list): Liste des infos de sortie avec toutes les versions

    Returns:
        list: Liste filtrée avec uniquement les dernières versions complètes
    """
    # Groupe par layer (project + sequence + shot + layer_name)
    layers_dict = {}

    for info in output_info:
        layer_key = (
            info.get("project", ""),
            info.get("sequence", ""),
            info.get("shot", ""),
            info.get("layer_name", ""),
        )

        if layer_key not in layers_dict:
            layers_dict[layer_key] = []
        layers_dict[layer_key].append(info)

    # Pour chaque layer, sélectionne la dernière version complète
    selected_versions = []

    for layer_key, versions in layers_dict.items():
        # Filtre les versions complètes (100%)
        complete_versions = [v for v in versions if v.get("completion", 0) == 100]

        if complete_versions:
            # Trie par version number (décroissant) et prend la plus récente
            latest = max(complete_versions, key=lambda x: x.get("version", 0))
            selected_versions.append(latest)
            addLog(f"  {latest.get('layer_name')}: v{latest.get('version'):03d} (100%)")
        else:
            # Si aucune version complète, prend la dernière version disponible
            latest = max(versions, key=lambda x: x.get("version", 0))
            selected_versions.append(latest)
            completion = latest.get("completion", 0)
            addLog(
                f"  {latest.get('layer_name')}: v{latest.get('version'):03d} ({completion}%) - ATTENTION: incomplet!"
            )

    return selected_versions


def generate_versioninfo(scenefile_path, sequence, shot, department, version_number):
    """
    Generates version information for the slap comp.

    Args:
        scenefile_dir (str): Path to scenefile directory
        sequence (str): Sequence name
        shot (str): Shot name
        department (str): Department name (e.g., 'Compo')
        version_number (int): Version number
    """

    path = os.path.normpath(scenefile_path)
    project_path_parts = path.split(os.sep)[0:2]
    project_path = os.sep.join(project_path_parts)

    # Extract version info
    versioninfo = {
        "project_path": project_path,
        "sequence": sequence,
        "shot": shot,
        "department": department,
        "task": "SlapComp",
        "version": f"v{version_number:03d}",
        "type": "shot",
        "locations": {"global": scenefile_path},
        "hierarchy": f"{sequence}/{shot}",
        "itemType": "shot",
        "comment": f"Automatically generated slap comp at : {datetime.datetime.now()}",
        "username": get_deadline_username(),
        "user": get_deadline_user_short(),
    }

    addLog("\n Version info collected: ")
    addLog(f"Project path: {versioninfo['project_path']}")
    addLog(f"Sequence: {versioninfo['sequence']}")
    addLog(f"department: {versioninfo['department']}")
    addLog(f"Task: {versioninfo['task']}")
    addLog(f"Version: {versioninfo['version']}")
    addLog(f"Type: {versioninfo['type']}")
    addLog(f"Hierarchy: {versioninfo['hierarchy']}")
    addLog(f"Username: {versioninfo['username']}")
    addLog(f"User: {versioninfo['user']}")
    addLog(f"Locations: {versioninfo['locations']}")

    # Create json file
    json_path = os.path.splitext(scenefile_path)[0] + "_versioninfo.json"
    with open(json_path, "w+") as f:
        json.dump(versioninfo, f, indent=2)

    addLog(f"Version info saved: {json_path}")

    return versioninfo


def get_deadline_username():

    user_info = ClientUtils.GetDeadlineUser()
    return user_info if user_info else "Unknown"


def get_deadline_user_short():

    full_name = ClientUtils.GetDeadlineUser()
    addLog(f"Full name: {full_name}")
    if full_name:
        # Extract initials or first 3 chars
        parts = full_name.split(".")
        addLog(f"Parts: {parts}")
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).lower()  # e.g., "am" for "Andrew Mansour"
        else:
            return full_name[:3].lower()  # e.g., "and" for "Andrew"
