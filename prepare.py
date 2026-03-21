from python.helpers import dotenv, runtime, settings
import asyncio
import string
import random
import resource
from python.helpers.print_style import PrintStyle


# Raise the file-descriptor soft limit to avoid "Too many open files" from LanceDB/Cognee
_FD_TARGET = 65536
try:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < _FD_TARGET:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(_FD_TARGET, hard), hard))
        new_soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        PrintStyle.standard(f"Raised file descriptor limit: {soft} -> {new_soft}")
except Exception as e:
    PrintStyle.warning(f"Could not raise file descriptor limit: {e}")

PrintStyle.standard("Preparing environment...")

try:

    runtime.initialize()

    # generate random root password if not set (for SSH)
    root_pass = dotenv.get_dotenv_value(dotenv.KEY_ROOT_PASSWORD)
    if not root_pass:
        root_pass = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        PrintStyle.standard("Changing root password...")
    settings.set_root_password(root_pass)

    # Initialize Cognee memory system — must succeed, it's the foundation
    import time as _time
    from python.helpers.cognee_init import init_cognee

    _COGNEE_MAX_RETRIES = 3
    _COGNEE_RETRY_DELAY = 2  # seconds

    for attempt in range(1, _COGNEE_MAX_RETRIES + 1):
        try:
            asyncio.get_event_loop().run_until_complete(init_cognee())
            from python.helpers.cognee_background import CogneeBackgroundWorker
            CogneeBackgroundWorker.get_instance().start()
            break
        except Exception as e:
            PrintStyle.error(f"Cognee init attempt {attempt}/{_COGNEE_MAX_RETRIES} failed: {e}")
            if attempt < _COGNEE_MAX_RETRIES:
                PrintStyle.standard(f"Retrying in {_COGNEE_RETRY_DELAY}s...")
                _time.sleep(_COGNEE_RETRY_DELAY)
                from python.helpers.memory import reload
                reload()
            else:
                raise RuntimeError(
                    f"Cognee initialization failed after {_COGNEE_MAX_RETRIES} attempts. "
                    f"Last error: {e}"
                )

except Exception as e:
    PrintStyle.error(f"Error in preload: {e}")
