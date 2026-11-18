from employer_buddy.ai import AIRefusalError, AIResult, SourceDocument
from employer_buddy.profile_schema import Experience, ProfileData, ProfileUpdate, empty_profile


def sample_profile() -> ProfileData:
    profile = empty_profile()
    profile.full_name = "Persona de Ejemplo"
    profile.experiences = [
        Experience(
            role="Analista de datos",
            company="Empresa Ejemplo",
            location="Bogotá",
            start="2021-03",
            end="",
            current=True,
            summary="Reportes de ventas",
            achievements=["Automaticé 12 reportes semanales"],
        )
    ]
    profile.skills = ["SQL", "Power BI"]
    return profile


class FakeAI:
    def __init__(self, questions=None, refuse=False):
        self.questions = list(questions or [])
        self.refuse = refuse
        self.calls: list[tuple] = []

    def _result(self, profile: ProfileData, questions: list[str]) -> AIResult:
        if self.refuse:
            raise AIRefusalError("refusal")
        return AIResult(
            update=ProfileUpdate(profile=profile, questions=questions),
            model="claude-opus-5-5",
            input_tokens=1000,
            output_tokens=200,
            request_id="req_test",
        )

    def extract(self, source: SourceDocument, current):
        self.calls.append(("extract", source, current))
        return self._result(sample_profile(), self.questions)

    def apply_answer(self, current, question, answer):
        self.calls.append(("apply_answer", question, answer))
        profile = current.model_copy(deep=True)
        profile.preferences.target_roles = [answer]
        return self._result(profile, self.questions[1:])
