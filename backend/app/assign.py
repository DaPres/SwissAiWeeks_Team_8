"""Load-balanced assignee policy for the blind eval (the approach of Main2/triagemate/assign.py).

The training `Assignee` is independent of service, team and ticket text: all 30 agents appear under every service with
a ~1/30 share each, so no model can predict it. Instead of guessing, pick from the real agent pool by an explainable,
deterministic policy:
  1. spread       - fewest tickets already assigned in this batch
  2. backlog      - then the smallest open / in-progress queue in the history
  3. familiarity  - then the most resolved tickets on this service (weak tie-break)
  4. stable hash  - final tie-break on the ticket text, so repeated runs give the same answer
"""
import collections
import hashlib
from dataclasses import dataclass, field
from functools import lru_cache

OPEN_STATUSES = ("open", "in progress")


@dataclass
class Assigner:
    pool: list[str]
    backlog: collections.Counter                        # agent -> open / in-progress tickets in the history
    familiarity: dict[str, collections.Counter]         # service -> agent -> resolved tickets
    session_load: collections.Counter = field(default_factory=collections.Counter)  # assignments in this batch

    @classmethod
    def from_training(cls, tickets: list[dict]) -> "Assigner":
        backlog: collections.Counter = collections.Counter()
        familiarity: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for t in tickets:
            agent = t.get("Assignee")
            if not agent:
                continue
            services = t.get("Affected Business or IT Services") or []
            if (t.get("Status") or "").lower() in OPEN_STATUSES:
                backlog[agent] += 1
            elif services:
                familiarity[services[0]][agent] += 1
        pool = sorted({t["Assignee"] for t in tickets if t.get("Assignee")})
        return cls(pool, backlog, dict(familiarity))

    def session(self) -> "Assigner":
        """A fresh batch over the same history (the history counters are shared read-only)."""
        return Assigner(self.pool, self.backlog, self.familiarity)

    def pick(self, service: str, seed: str) -> tuple[str | None, str]:
        if not self.pool:
            return None, "no assignee pool available"
        fam = self.familiarity.get(service, collections.Counter())

        def key(agent: str) -> tuple:
            h = hashlib.sha1(f"{seed}|{agent}".encode()).hexdigest()
            return self.session_load[agent], self.backlog[agent], -fam[agent], h

        best = min(self.pool, key=key)
        self.session_load[best] += 1
        return best, (f"least-loaded agent (open backlog {self.backlog[best]}, {self.session_load[best]} in this batch; "
                      f"{fam[best]} resolved {service} tickets) - historical assignment is independent of the ticket, "
                      f"so the batch is load-balanced")


@lru_cache(maxsize=1)
def history_assigner() -> Assigner:
    from .curation import training_tickets

    return Assigner.from_training(training_tickets())
