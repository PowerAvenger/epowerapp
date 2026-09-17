import unittest
from unittest.mock import Mock, patch

from backend_github_actions import lanzar_workflows_mercado


class TestGithubActions(unittest.TestCase):
    @staticmethod
    def respuesta_sin_ejecuciones():
        respuesta = Mock(status_code=200)
        respuesta.json.return_value = {"workflow_runs": []}
        return respuesta

    def test_lanza_spot_y_ssaa_en_master(self):
        respuesta = Mock(status_code=204)
        with patch(
            "backend_github_actions.requests.get",
            return_value=self.respuesta_sin_ejecuciones(),
        ), patch("backend_github_actions.requests.post", return_value=respuesta) as post:
            resultados = lanzar_workflows_mercado("token-prueba")

        self.assertEqual(
            [resultado.nombre for resultado in resultados], ["SPOT", "SSAA"]
        )
        self.assertTrue(all(resultado.lanzado for resultado in resultados))
        self.assertEqual(post.call_count, 2)
        self.assertTrue(all(
            llamada.kwargs["json"] == {"ref": "master"}
            for llamada in post.call_args_list
        ))
        self.assertTrue(all(
            llamada.kwargs["headers"]["Authorization"] == "Bearer token-prueba"
            for llamada in post.call_args_list
        ))

    def test_informa_del_workflow_rechazado(self):
        aceptada = Mock(status_code=204)
        rechazada = Mock(status_code=403)
        rechazada.json.return_value = {"message": "Resource not accessible"}
        with patch(
            "backend_github_actions.requests.get",
            return_value=self.respuesta_sin_ejecuciones(),
        ), patch(
            "backend_github_actions.requests.post",
            side_effect=[aceptada, rechazada],
        ):
            resultados = lanzar_workflows_mercado("token-prueba")

        self.assertTrue(resultados[0].lanzado)
        self.assertFalse(resultados[1].lanzado)
        self.assertEqual(resultados[1].detalle, "Resource not accessible")

    def test_no_duplica_un_workflow_activo(self):
        ejecuciones = Mock(status_code=200)
        ejecuciones.json.return_value = {
            "workflow_runs": [
                {
                    "status": "in_progress",
                    "html_url": "https://github.com/run/123",
                }
            ]
        }
        with patch(
            "backend_github_actions.requests.get", return_value=ejecuciones
        ), patch("backend_github_actions.requests.post") as post:
            resultados = lanzar_workflows_mercado("token-prueba")

        self.assertTrue(all(not resultado.lanzado for resultado in resultados))
        self.assertTrue(all("en cola o en curso" in resultado.detalle for resultado in resultados))
        post.assert_not_called()

    def test_exige_token(self):
        with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN_IDS_REE"):
            lanzar_workflows_mercado("")
