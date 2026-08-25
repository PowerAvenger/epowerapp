import unittest

from backend_curvadecarga import AXON_RETRY_STATUS, crear_sesion_axon


class AxonReintentosTest(unittest.TestCase):
    def test_sesion_reintenta_errores_temporales(self):
        with crear_sesion_axon() as sesion:
            retry = sesion.get_adapter("https://").max_retries
            self.assertEqual(retry.total, 3)
            self.assertEqual(retry.status, 3)
            self.assertEqual(retry.backoff_factor, 0.75)
            self.assertEqual(set(retry.status_forcelist), set(AXON_RETRY_STATUS))
            self.assertIn("GET", retry.allowed_methods)


if __name__ == "__main__":
    unittest.main()
