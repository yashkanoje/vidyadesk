"""Owner actions shared by the Telegram commands, the command line and the dashboard."""
from leadagent.agent.graph import get_checkpointer
from leadagent.locks import lock_for
from leadagent.store import repo


def delete_lead_and_history(session, lead) -> None:
    """Delete a lead, its messages and its chat state. Waits for any reply being written for it."""
    lead_id = lead.id
    with lock_for(lead_id):
        repo.delete_lead(session, lead)
        session.flush()
        get_checkpointer().delete_thread(str(lead_id))
