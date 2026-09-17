"""Lanzamiento remoto de las actualizaciones de mercado en GitHub Actions."""

from dataclasses import dataclass

import requests


GITHUB_API = "https://api.github.com"
REPOSITORIO_IDS_REE = "PowerAvenger/ids_ree"
RAMA_IDS_REE = "master"
WORKFLOWS_MERCADO = {
    "SPOT": "actualizar_spot.yml",
    "SSAA": "actualizar_ssaa.yml",
}
ESTADOS_ACTIVOS = {"queued", "in_progress", "waiting", "pending", "requested"}


@dataclass(frozen=True)
class ResultadoWorkflow:
    nombre: str
    workflow: str
    lanzado: bool
    detalle: str
    url: str


def lanzar_workflows_mercado(token, *, timeout=15):
    """Pone en cola las actualizaciones manuales de SPOT y SSAA."""
    token = str(token or "").strip()
    if not token:
        raise ValueError("Falta el secreto GITHUB_TOKEN_IDS_REE.")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resultados = []
    for nombre, workflow in WORKFLOWS_MERCADO.items():
        workflow_url = (
            f"{GITHUB_API}/repos/{REPOSITORIO_IDS_REE}/actions/"
            f"workflows/{workflow}"
        )
        api_url = (
            f"{workflow_url}/dispatches"
        )
        web_url = (
            f"https://github.com/{REPOSITORIO_IDS_REE}/actions/"
            f"workflows/{workflow}"
        )
        try:
            ejecuciones = requests.get(
                f"{workflow_url}/runs",
                headers=headers,
                params={"per_page": 10},
                timeout=timeout,
            )
            ejecuciones.raise_for_status()
            activa = next(
                (
                    run for run in ejecuciones.json().get("workflow_runs", [])
                    if run.get("status") in ESTADOS_ACTIVOS
                ),
                None,
            )
            if activa:
                resultados.append(
                    ResultadoWorkflow(
                        nombre,
                        workflow,
                        False,
                        "Ya hay una ejecución en cola o en curso.",
                        activa.get("html_url") or web_url,
                    )
                )
                continue

            respuesta = requests.post(
                api_url,
                headers=headers,
                json={"ref": RAMA_IDS_REE},
                timeout=timeout,
            )
            lanzado = respuesta.status_code in {200, 201, 204}
            if lanzado:
                detalle = "Solicitud aceptada por GitHub."
            else:
                try:
                    detalle = respuesta.json().get("message", respuesta.text)
                except ValueError:
                    detalle = respuesta.text
                detalle = detalle.strip() or f"HTTP {respuesta.status_code}"
        except requests.RequestException as exc:
            lanzado = False
            detalle = f"No se pudo contactar con GitHub: {exc}"

        resultados.append(
            ResultadoWorkflow(nombre, workflow, lanzado, detalle, web_url)
        )
    return resultados
