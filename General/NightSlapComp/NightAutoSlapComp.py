from Deadline.Scripting import RepositoryUtils  # type: ignore
from Deadline import Jobs  # type: ignore
from System import DateTime  # type: ignore

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
import slapcomp  # noqa: E402

if "slapcomp" in sys.modules:
    importlib.reload(slapcomp)


class NightSlap:
    def __init__(self):

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

        slapcomp.add_log(f"Data: {data}")

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

        slapcomp.add_log(f"Checking min datetime: {min_date}, max datetime: {max_date}")
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
    slapcomp.add_log(f"Found {len(night_jobs)} to process")
    slapcomp.auto_slap(night_jobs)


if __name__ == "__main__":
    __main__()
