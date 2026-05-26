def main():
    pass


def auto_slap(selected_jobs: list):
    from . import SlapCompCore

    SlapCompCore.autoSlapIt(selected_jobs)


def add_log(msg: str):
    from . import SlapCompCore

    SlapCompCore.addLog(msg)

def get_selected_jobs():
    from . import SlapCompCore

    SlapCompCore.get_selected_jobs()

def get_job_batch(batch_name):
    from . import SlapCompCore

    SlapCompCore.get_job_batch(batch_name)

def get_output_dirs(jobs_to_process):
    from . import SlapCompCore

    SlapCompCore.get_output_dirs(jobs_to_process)  

def call_nuke_script(ordered_output_info, render_mode):
    from . import SlapCompCore

    SlapCompCore.call_nuke_script(ordered_output_info, render_mode)  

def show_slap_comp_ui_dialog(output_info):
    from . import SlapCompUI_Qt

    SlapCompUI_Qt.show_slap_comp_dialog(output_info)