from Deadline.Scripting import RepositoryUtils
from Deadline import Jobs
from System import DateTime

import sys
import os
import json
import importlib

# Ajoute le chemin du dossier General pour importer les modules
repo_path = RepositoryUtils.GetRootDirectory()
general_scripts_path = os.path.join(repo_path, "custom", "scripts", "General")
if general_scripts_path not in sys.path:
    sys.path.insert(0, general_scripts_path)

# Import du module commun
import SlapCompCore

if "SlapCompCore" in sys.modules:
    importlib.reload(SlapCompCore)

# TODO: Move it to SlapCompCore and update autoSlapIt.py
def autoSlapIt(selected_jobs: list):

    processed_slaps = []

    for i, job in enumerate(selected_jobs):
        SlapCompCore.addLog(f"\n{'=' * 60}")
        SlapCompCore.addLog(f"Processing job number : {i + 1}\n{job.JobName}")
        SlapCompCore.addLog(f"{'=' * 60}")

        jobs_to_process = []
        processed_batches = set()

        batch_name = job.JobBatchName

        if batch_name and batch_name not in processed_batches:
            batch_jobs = SlapCompCore.get_job_batch(batch_name)
            # SlapCompCore.addLog(f"Detected {len(batch_jobs)} job(s) in the batch")
            jobs_to_process.extend(batch_jobs)
            processed_batches.add(batch_name)
        elif not batch_name:
            jobs_to_process.append(job)

        output_info = SlapCompCore.get_output_dirs(jobs_to_process)
        # SlapCompCore.addLog(f"\n{len(output_info)} sequence(s) trouvee(s)")
        if len(output_info) == 0:
            SlapCompCore.addLog("Aucune sequence trouvee")
            continue

        SlapCompCore.addLog(
            "\n=== Selection automatique des dernieres versions completes ==="
        )
        output_info = SlapCompCore.select_latest_complete_versions(output_info)
        if len(output_info) == 0:
            SlapCompCore.addLog("Erreur: aucune version selectionnee")
            continue

        # === AUTOMATION: Application automatique des presets ===
        SlapCompCore.addLog("\n=== Application des presets ===")
        # Extrait project/sequence/shot du premier item
        first_info = output_info[0]
        project = first_info.get("project", "")
        sequence = first_info.get("sequence", "")
        shot = first_info.get("shot", "")

        slap_name = "_".join([project, shot, sequence])
        if slap_name in processed_slaps:
            continue
        processed_slaps.append(slap_name)

        # Charge et applique le preset
        preset_data = SlapCompCore.load_preset(project, sequence, shot)
        if preset_data:
            ordered_output_info = SlapCompCore.apply_preset_data(
                output_info, preset_data
            )
            SlapCompCore.addLog("\nOrdre des layers applique depuis preset:")
            for idx, info in enumerate(ordered_output_info):
                layer_name = info.get("layer_name", "Unknown")
                merge_op = info.get("merge_operation", "over")
                SlapCompCore.addLog(f"  [{idx}] {layer_name} (merge: {merge_op})")
        else:
            # ordered_output_info = output_info
            SlapCompCore.addLog("Preset not found -- SKIPPING SLAPCOMP")
            continue

        # Ajoute les index de compositing
        for idx, item in enumerate(ordered_output_info):
            item["compositing_index"] = idx

        # === AUTOMATION: Soumission automatique à Deadline ===
        SlapCompCore.addLog("\n=== Soumission automatique a Deadline ===")
        render_mode = "deadline"  # Force le mode Deadline

        SlapCompCore.addLog("\nOrdre final:")
        for item in ordered_output_info:
            layer_name = item.get(
                "layer_name", os.path.basename(item.get("directory", "Unknown"))
            )
            merge_op = item.get("merge_operation", "over")
            SlapCompCore.addLog(
                f"  [{item['compositing_index']}] {layer_name} (merge: {merge_op})"
            )

        SlapCompCore.call_nuke_script(ordered_output_info, render_mode)
        SlapCompCore.addLog(f"SlapComp submitted for {job.JobName}\n")


class NightSlap:
    def __init__(self):

        print("Initialize the tong")

        self.config_file = self.getConfigFile()

        self.min_time, self.max_time, self.project_exclude, self.user_exclude = (
            self.getConfigData()
        )
        self.min_date, self.max_date = self.getDateTimeFromTime()

    def getConfigFile(self):

        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(base_dir, "config.json")

        return config_file

    def getConfigData(self):

        with open(self.config_file) as f:
            data = json.load(f)

        SlapCompCore.addLog(f"Data: {data}")

        return (
            data["min_time"],
            data["max_time"],
            data["project_exclude"],
            data["user_exclude"],
        )

    def getDateTimeFromTime(self):

        today = DateTime.Today
        max_date = DateTime(today.Year, today.Month, today.Day, self.max_time, 0, 0)

        # if min time is greater than max time, check that time for yesterday
        if self.min_time >= self.max_time:
            yesterday = today.AddDays(-1)
            min_date = DateTime(
                yesterday.Year, yesterday.Month, yesterday.Day, self.min_time, 0, 0
            )
        else:
            min_date = DateTime(today.Year, today.Month, today.Day, self.min_time, 0, 0)

        SlapCompCore.addLog(
            f"Checking min datetime: {min_date}, max datetime: {max_date}"
        )
        return min_date, max_date

    def betweenDates(self, submit_date_time: DateTime):
        return submit_date_time > self.min_date and submit_date_time < self.max_date

    def isValidJob(self, job: Jobs.Job):

        # TODO: not in, and len > 0 only here temporarily.
        if job.JobUserName in self.user_exclude:
            return False

        if job.JobPool in self.project_exclude:
            return False

        return "Prism-Submission-Python" in job.JobComment

    def getNightJobs(self):
        all_jobs = RepositoryUtils.GetJobs(True)
        night_jobs = [
            job
            for job in all_jobs
            if (self.betweenDates(job.JobCompletedDateTime) and self.isValidJob(job))
        ]

        return night_jobs


def __main__():

    night_slap = NightSlap()
    night_jobs = night_slap.getNightJobs()

    # apply autoslap
    SlapCompCore.addLog(f"Found {len(night_jobs)} to process")
    autoSlapIt(night_jobs)


if __name__ == "__main__":
    __main__()
