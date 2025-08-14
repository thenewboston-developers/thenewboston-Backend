from .database import apply_on_commit


def run_task_on_commit(task, *args, **kwargs):
    def no_args_callable():
        task.delay(*args, **kwargs)

    apply_on_commit(no_args_callable)
