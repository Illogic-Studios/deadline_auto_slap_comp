def main():
    pass


def auto_slap(selected_jobs: list):
    from . import SlapCompCore

    SlapCompCore.autoSlapIt(selected_jobs)


def add_log(msg: str):
    from . import SlapCompCore

    SlapCompCore.addLog(msg)
