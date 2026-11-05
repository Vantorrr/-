from dataclasses import dataclass


@dataclass
class SubmitResult:
    ok: bool
    external_result_id: str | None
    detail: str


class SubmitAdapter:
    """No current source has a permitted automated submit API."""

    def __init__(self, source_id: str):
        self.source_id = source_id
        self.can_submit = False
        self.name = "manual"

    def submit(self, listing) -> SubmitResult:
        return SubmitResult(ok=False, external_result_id=None, detail="no permitted submit API")


def adapter_for(source_id: str) -> SubmitAdapter:
    return SubmitAdapter(source_id)
