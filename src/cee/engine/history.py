"""
Záznam průběhu simulace — trasovatelnost jednoho slova (CEE_master.md, Etapa 1).

Simulátor sám vrací jen konečné stavy. Bez záznamu nelze odpovědět na otázky,
kvůli kterým projekt vzniká: *čím* slovo prošlo, *kdy*, a co do jeho podoby
promluvilo. Tenhle modul ten průběh zachytí, aniž by do enginu vnášel
prezentační logiku.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WordChange:
    """Dopad jednoho pravidla na jedno slovo."""

    concept_id: str
    before: str
    after: str

    @property
    def deleted(self) -> bool:
        return self.after == ""

    def as_dict(self) -> Dict[str, Any]:
        return {"concept_id": self.concept_id, "before": self.before, "after": self.after}


@dataclass
class RuleApplication:
    """Jedno pravidlo v jednom uzlu v jednom roce, včetně toho, co změnilo."""

    year: int
    node_id: str
    rule_name: str
    target: Dict[str, str]
    action: Dict[str, str]
    env_before: Optional[Dict[str, str]] = None
    env_after: Optional[Dict[str, str]] = None
    generated: bool = False
    changes: List[WordChange] = field(default_factory=list)

    @property
    def hit_count(self) -> int:
        return len(self.changes)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": "sound_change",
            "year": self.year,
            "node_id": self.node_id,
            "rule_name": self.rule_name,
            "target": self.target,
            "action": self.action,
            "env_before": self.env_before,
            "env_after": self.env_after,
            "generated": self.generated,
            "hit_count": self.hit_count,
            "changes": [c.as_dict() for c in self.changes],
        }


@dataclass
class BorrowingEvent:
    """Horizontální přenos — slova přejatá z jiného jazyka."""

    year: int
    source_id: str
    target_id: str
    concepts: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": "borrowing",
            "year": self.year,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "concepts": self.concepts,
        }


@dataclass
class SplitEvent:
    """Odštěpení dceřiného jazyka od rodiče."""

    year: int
    parent_id: str
    child_id: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": "split",
            "year": self.year,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
        }


@dataclass
class Snapshot:
    """Stav jazyka v jednom okamžiku — jedna epocha na časové ose."""

    year: int
    node_id: str
    words: Dict[str, str]
    inventory: List[str] = field(default_factory=list)
    label: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "node_id": self.node_id,
            "label": self.label,
            "words": self.words,
            "inventory": self.inventory,
        }


@dataclass
class TraceStep:
    """Jeden krok v derivaci slova: co se stalo a proč."""

    year: int
    form: str
    rule_name: Optional[str] = None
    note: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "form": self.form,
            "rule_name": self.rule_name,
            "note": self.note,
        }


@dataclass
class SimulationHistory:
    """
    Kompletní průběh běhu. Události jsou v chronologickém pořadí, tak jak je
    simulátor zpracoval — pořadí je součástí informace, ne detail.
    """

    events: List[Any] = field(default_factory=list)
    snapshots: List[Snapshot] = field(default_factory=list)

    def record(self, event) -> None:
        self.events.append(event)

    def snapshot(self, snap: Snapshot) -> None:
        self.snapshots.append(snap)

    def rule_applications(self, node_id: Optional[str] = None) -> List[RuleApplication]:
        return [
            e
            for e in self.events
            if isinstance(e, RuleApplication) and (node_id is None or e.node_id == node_id)
        ]

    def borrowings(self, node_id: Optional[str] = None) -> List[BorrowingEvent]:
        return [
            e
            for e in self.events
            if isinstance(e, BorrowingEvent) and (node_id is None or e.target_id == node_id)
        ]

    def snapshots_for(self, node_id: str) -> List[Snapshot]:
        return [s for s in self.snapshots if s.node_id == node_id]

    def trace(self, node_id: str, concept_id: str) -> List[TraceStep]:
        """
        Derivace jednoho slova v jednom jazyce: posloupnost tvarů i s pravidlem,
        které každý krok způsobilo. Kroky bez zásahu se nezaznamenávají — do
        derivace patří jen to, co tvar skutečně změnilo.
        """
        steps: List[TraceStep] = []

        for event in self.events:
            if isinstance(event, RuleApplication):
                if event.node_id != node_id:
                    continue
                for change in event.changes:
                    if change.concept_id != concept_id:
                        continue
                    if not steps:
                        steps.append(TraceStep(year=event.year, form=change.before,
                                               note="výchozí tvar"))
                    steps.append(
                        TraceStep(
                            year=event.year,
                            form=change.after if change.after else "∅",
                            rule_name=event.rule_name,
                        )
                    )

            elif isinstance(event, BorrowingEvent):
                if event.target_id == node_id and concept_id in event.concepts:
                    steps.append(
                        TraceStep(
                            year=event.year,
                            form="",
                            note=f"přejato z '{event.source_id}'",
                        )
                    )

        return steps

    def as_dict(self) -> Dict[str, Any]:
        return {
            "events": [e.as_dict() for e in self.events],
            "snapshots": [s.as_dict() for s in self.snapshots],
        }
