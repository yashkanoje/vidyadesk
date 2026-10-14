from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FactsError(ValueError):
    """Institute facts are missing or invalid. The message is safe to show to an owner."""


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    for_classes: str = Field(min_length=1)
    fee: str = Field(min_length=1)
    batches: list[str] = Field(min_length=1)


class Faq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1)
    a: str = Field(min_length=1)


class Facts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    institute_name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    timings: str = Field(min_length=1)
    courses: list[Course] = Field(min_length=1)
    faq: list[Faq] = []


def parse_facts(data) -> Facts:
    try:
        return Facts.model_validate(data)
    except ValidationError as exc:
        lines = [f"{'.'.join(str(part) for part in err['loc']) or 'file'}: {err['msg']}" for err in exc.errors()]
        raise FactsError("Invalid institute facts:\n" + "\n".join(lines)) from exc


def load_facts_file(path: Path) -> Facts:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FactsError(f"{path} is not valid YAML: {exc}") from exc
    return parse_facts(data)


def render_facts(facts: Facts) -> str:
    lines = [
        f"Institute: {facts.institute_name}",
        f"Address: {facts.address}",
        f"Phone: {facts.phone}",
        f"Office timings: {facts.timings}",
        "",
        "Courses:",
    ]
    for course in facts.courses:
        lines.append(
            f"- {course.name} (for {course.for_classes}). Fee: {course.fee}. "
            f"Batches: {'; '.join(course.batches)}"
        )
    if facts.faq:
        lines += ["", "Frequently asked questions:"]
        lines += [f"- Q: {item.q} A: {item.a}" for item in facts.faq]
    return "\n".join(lines)
