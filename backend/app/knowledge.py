"""Building and growing the knowledge base.

Initial learning: the 20k history is curated (scored, clustered, levelled - see curation.py) and clusters at or
above the chosen quality level are published, plus one catalog card per service.
Continuous learning: every ticket resolved in this system becomes a `live` knowledge item.

CLI:  uv run python -m app.knowledge [--level silver]  # curate + publish history, rebuild catalog
      uv run python -m app.knowledge --reembed         # re-embed everything, e.g. after switching embedding model
"""
import argparse
import logging
import re
import time

from . import catalog
from .config import settings
from .curation import publish, run_curation
from .llm import get_llm
from .store import Store

log = logging.getLogger(__name__)

DEFAULT_MIN_LEVEL = "gold"


def embedding_text(item: dict) -> str:
    """What gets vectorised. Training summaries/descriptions are generic templates; the resolution names the
    actual problem class (e.g. "broken broker routing link after the account switch"), so it is embedded too."""
    return item["problem"] + (f"\nResolution: {item['resolution']}" if item.get("resolution") else "")


def catalog_items() -> list[dict]:
    return [
        {
            "id": "catalog-" + re.sub(r"[^a-z]+", "-", name.lower()).strip("-"),
            "source": "catalog",
            "service": name,
            "team": team,
            "title": f"Service catalog: {name}",
            "problem": f"{name} ({'critical' if critical else 'non-critical'} service, owned by {team}). {desc}",
        }
        for name, (team, critical, desc) in catalog.SERVICES.items()
    ]


def ingest(store: Store, min_level: str | None = None) -> dict:
    llm = get_llm()
    t0 = time.time()
    items = catalog_items()
    store.delete_knowledge_source("catalog")
    store.add_knowledge(items, llm.embed([embedding_text(i) for i in items]))
    run_curation(store)
    publish(store, min_level or store.get_meta("knowledge_min_level") or DEFAULT_MIN_LEVEL)
    store.set_meta("embedding_model", llm.embedding_model)
    log.info("knowledge built in %.1fs: %s", time.time() - t0, store.knowledge_stats())
    return store.knowledge_stats()


def reembed(store: Store) -> None:
    llm = get_llm()
    items = store.all_knowledge_for_reembed()
    if items:
        store.add_knowledge(items, llm.embed([embedding_text(i) for i in items]))
    tickets = store.list_tickets()
    if tickets:
        vecs = llm.embed([ticket_text(t) for t in tickets])
        for t, v in zip(tickets, vecs):
            store.update_ticket(t["id"], {"embedding": v.tobytes()})
    store.set_meta("embedding_model", llm.embedding_model)


def ensure_ready(store: Store) -> None:
    """Called at startup: first run ingests; an embedding-model change re-embeds (vectors aren't comparable)."""
    current = store.get_meta("embedding_model")
    if current is None or store.curation_summary() is None:
        ingest(store)
    elif current != get_llm().embedding_model:
        log.warning("embedding model changed %s -> %s; re-embedding", current, get_llm().embedding_model)
        reembed(store)


def ticket_text(t: dict) -> str:
    images = t.get("image_descriptions") or []
    return "\n".join([t["summary"], t["description"], *(f"Screenshot: {d}" for d in images)])


def learn_from_ticket(store: Store, ticket: dict) -> str:
    """Continuous learning: a resolved ticket becomes retrievable knowledge for the next user."""
    item = {
        "id": f"live-{ticket['id']}",
        "source": "live",
        "service": ticket["service"],
        "team": ticket["team"],
        "work_type": ticket["work_type"],
        "resolver": ticket["assignee"],
        "title": ticket["summary"],
        "problem": ticket_text(ticket),
        "resolution": ticket["resolution_text"],
        "ticket_id": ticket["id"],
    }
    store.add_knowledge([item], get_llm().embed([embedding_text(item)]))
    return item["id"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--reembed", action="store_true")
    parser.add_argument("--level", choices=["gold", "silver", "bronze"], help="minimum cluster quality level to publish")
    args = parser.parse_args()
    s = Store(settings.db_path)
    if args.reembed:
        reembed(s)
    else:
        print(ingest(s, args.level))
    print(s.knowledge_stats())
