"""Estructura del perfil maestro. También es el esquema que Claude debe devolver.

Los datos que faltan se guardan como texto vacío en lugar de null: cada campo opcional
multiplica el tamaño de la gramática de salida estructurada y la API la rechaza si crece demasiado.
"""

from pydantic import BaseModel, Field

DATE_HINT = "Formato AAAA-MM, o AAAA si solo aparece el año. Vacío si no aparece."


class Experience(BaseModel):
    role: str = Field(description="Cargo")
    company: str = Field(description="Empresa")
    location: str = Field(description="Ciudad o país. vacío si no aparece.")
    start: str = Field(description=f"Fecha de inicio. {DATE_HINT}")
    end: str = Field(description=f"Fecha de fin. {DATE_HINT} vacío si es el trabajo actual.")
    current: bool = Field(description="true si es el trabajo actual")
    summary: str = Field(description="Responsabilidades principales, tal como aparecen")
    achievements: list[str] = Field(description="Logros concretos, conservando las cifras")


class Education(BaseModel):
    degree: str = Field(description="Título o programa")
    institution: str
    start: str = Field(description=DATE_HINT)
    end: str = Field(description=DATE_HINT)
    status: str = Field(description="Graduado, en curso, incompleto. vacío si no aparece.")


class Course(BaseModel):
    name: str = Field(description="Curso o certificación")
    issuer: str = Field(description="Entidad o plataforma que lo otorga")
    year: str = Field(description="Año. Vacío si no aparece.")
    status: str = Field(description="Finalizado o en curso. vacío si no aparece.")


class Language(BaseModel):
    language: str
    level: str = Field(description="Nivel tal como aparece (ej. B2, nativo, intermedio)")


class Preferences(BaseModel):
    target_roles: list[str] = Field(description="Cargos que busca")
    locations: list[str] = Field(description="Ciudades o países donde quiere trabajar")
    work_modes: list[str] = Field(description="Presencial, híbrido o remoto")
    salary_expectation: str = Field(description="Aspiración salarial, si la dio")


class ProfileData(BaseModel):
    full_name: str = Field(description="Vacío si no aparece")
    headline: str = Field(description="Título profesional corto, si aparece")
    location: str = Field(description="Vacío si no aparece")
    email: str = Field(description="Vacío si no aparece")
    phone: str = Field(description="Vacío si no aparece")
    links: list[str] = Field(description="LinkedIn, portafolio u otros enlaces")
    summary: str = Field(description="Perfil o resumen profesional, si aparece")
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
        full_name="",
        headline="",
        location="",
        email="",
        phone="",
        links=[],
        summary="",
        experiences=[],
        education=[],
        courses=[],
        skills=[],
        languages=[],
        preferences=Preferences(
            target_roles=[], locations=[], work_modes=[], salary_expectation=""
        ),
    )
