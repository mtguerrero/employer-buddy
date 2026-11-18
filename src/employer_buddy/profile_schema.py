"""Estructura del perfil maestro. También es el esquema que Claude debe devolver."""

from pydantic import BaseModel, Field

DATE_HINT = "Formato AAAA-MM, o AAAA si solo aparece el año. null si no aparece."


class Experience(BaseModel):
    role: str = Field(description="Cargo")
    company: str = Field(description="Empresa")
    location: str | None = Field(description="Ciudad o país. null si no aparece.")
    start: str | None = Field(description=f"Fecha de inicio. {DATE_HINT}")
    end: str | None = Field(description=f"Fecha de fin. {DATE_HINT} null si es el trabajo actual.")
    current: bool = Field(description="true si es el trabajo actual")
    summary: str | None = Field(description="Responsabilidades principales, tal como aparecen")
    achievements: list[str] = Field(description="Logros concretos, conservando las cifras")


class Education(BaseModel):
    degree: str = Field(description="Título o programa")
    institution: str
    start: str | None = Field(description=DATE_HINT)
    end: str | None = Field(description=DATE_HINT)
    status: str | None = Field(description="Graduado, en curso, incompleto. null si no aparece.")


class Course(BaseModel):
    name: str = Field(description="Curso o certificación")
    issuer: str | None = Field(description="Entidad que lo otorga")
    year: str | None


class Language(BaseModel):
    language: str
    level: str | None = Field(description="Nivel tal como aparece (ej. B2, nativo, intermedio)")


class Preferences(BaseModel):
    target_roles: list[str] = Field(description="Cargos que busca")
    locations: list[str] = Field(description="Ciudades o países donde quiere trabajar")
    work_modes: list[str] = Field(description="Presencial, híbrido o remoto")
    salary_expectation: str | None = Field(description="Aspiración salarial, si la dio")


class ProfileData(BaseModel):
    full_name: str | None
    headline: str | None = Field(description="Título profesional corto, si aparece")
    location: str | None
    email: str | None
    phone: str | None
    links: list[str] = Field(description="LinkedIn, portafolio u otros enlaces")
    summary: str | None = Field(description="Perfil o resumen profesional, si aparece")
    experiences: list[Experience]
    education: list[Education]
    courses: list[Course]
    skills: list[str]
    languages: list[Language]
    preferences: Preferences


class ProfileUpdate(BaseModel):
    profile: ProfileData
    questions: list[str] = Field(
        description=(
            "Preguntas pendientes para el usuario, en español, tuteando, una idea por "
            "pregunta, de la más importante a la menos importante. Máximo 5."
        )
    )


def empty_profile() -> ProfileData:
    return ProfileData(
        full_name=None,
        headline=None,
        location=None,
        email=None,
        phone=None,
        links=[],
        summary=None,
        experiences=[],
        education=[],
        courses=[],
        skills=[],
        languages=[],
        preferences=Preferences(
            target_roles=[], locations=[], work_modes=[], salary_expectation=None
        ),
    )
