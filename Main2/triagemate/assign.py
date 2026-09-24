"""Assignee policy.

Finding (reproduced by ``python -m triagemate.cli analyze``): in the 20k training tickets the assignee is
statistically independent of service, team, entity, work type, reporter, priority and resolution
(Cramer's V ~ 0.04 with chi-square ~ degrees of freedom, i.e. chance level; all 30 assignees serve all 11 teams).
No model can honestly *predict* the historical assignee, so we do not pretend to.

What we do instead is an explainable, testable **routing policy** over the real agent pool:
  1. spread         - fewest tickets already assigned in this run (a batch is spread across the pool)
  2. current load   - then the smallest historical open/in-progress backlog
  3. familiarity    - most previously resolved tickets on this service (weak, tie-breaking signal)
  4. stable hash    - deterministic final tie-break so repeated runs give the same answer
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .models import Ticket


@dataclass
class Assigner:
    pool: list[str] = field(default_factory=list)
    backlog: Counter = field(default_factory=Counter)                       # assignee -> open tickets (history)
    familiarity: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))   # service -> assignee -> done
    session_load: Counter = field(default_factory=Counter)                  # assignments made since start

    @classmethod
    def from_training(cls, tickets: list[Ticket]) -> "Assigner":
        a = cls()
        seen = set()
        for t in tickets:
            if not t.assignee:
                continue
            seen.add(t.assignee)
            if (t.status or "").lower() in ("open", "in progress"):
                a.backlog[t.assignee] += 1
            elif t.service:
                a.familiarity[t.service][t.assignee] += 1
        a.pool = sorted(seen)
        return a

    def load(self, agent: str) -> int:
        return self.backlog[agent] + self.session_load[agent]

    def pick(self, service: str, seed_text: str, commit: bool = True) -> tuple[str | None, str]:
        if not self.pool:
            return None, "no assignee pool available"
        fam = self.familiarity.get(service, Counter())

        def key(agent: str):
            h = hashlib.sha1(f"{seed_text}|{agent}".encode()).hexdigest()
            return (self.session_load[agent], self.backlog[agent], -fam[agent], h)   # spread a batch first, then lowest backlog

        best = min(self.pool, key=key)
        reason = (f"least-loaded agent in the pool (open workload {self.load(best)}; "
                  f"{fam[best]} previously resolved {service} tickets). Historical assignment is independent of service/team "
                  f"in the training data, so load-balancing is the defensible policy.")
        if commit:
            self.session_load[best] += 1
        return best, reason

    def release(self, agent: str) -> None:
        if self.session_load[agent] > 0:
            self.session_load[agent] -= 1
