# Backward-compatibility shim — real module lives in plugins/memory/helpers/
from plugins._memory.helpers.memory import *  # noqa: F401,F403
from plugins._memory.helpers.memory import (  # noqa: F401 — underscore names skipped by *
    _get_cognee,
    _extract_metadata_from_text,
    _subdir_to_dataset,
    _deduplicate_documents,
    _parse_filter_to_node_names,
    _results_to_documents,
    _delete_data_by_id,
)
