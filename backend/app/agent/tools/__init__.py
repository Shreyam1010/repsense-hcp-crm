"""The agent's toolset. Seven tools; the two
mandated ones are log_interaction and edit_interaction. get_hcp_history is a seventh."""
from .edit import edit_interaction
from .followups import suggest_follow_ups
from .log import log_interaction
from .reference import check_product_material, get_hcp_history, resolve_hcp
from .samples import record_sample_distribution

ALL_TOOLS = [
    log_interaction,
    edit_interaction,
    resolve_hcp,
    check_product_material,
    record_sample_distribution,
    suggest_follow_ups,
    get_hcp_history,
]

__all__ = ["ALL_TOOLS"]
