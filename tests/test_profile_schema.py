from datetime import date

from employer_buddy.profile_schema import Education, empty_profile, fill_education_status


def education(end: str, status: str = "") -> Education:
    return Education(degree="Programa", institution="Institución", start="", end=end, status=status)


def test_estudios_con_fin_pasado_quedan_finalizados():
    profile = empty_profile()
    profile.education = [
        education("2021-11"),
        education("2016"),
        education("2027-06"),
        education(""),
        education("2019-12", status="Incompleto"),
        education("sin fecha"),
    ]
    result = fill_education_status(profile, date(2026, 2, 1))
    assert [e.status for e in result.education] == [
        "Finalizado",
        "Finalizado",
        "",
        "",
        "Incompleto",
        "",
    ]
