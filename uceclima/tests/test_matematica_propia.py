# UCEclima Lambda 9.1.0 · © 2026 Diego Quishpe Landeta, Teresa Palacios y María Eugenia Ávila-Salem · GPL-3.0-or-later (ver LICENSE)
"""Pruebas de uceclima.matematica_propia: conservación, positividad, límites, casos secos, datos inválidos y convergencia."""
import math
import unittest
import numpy as np
from uceclima import matematica_propia as mp


def _tormenta(dt_h, dur_h=3.0, p_mm=90.0):
    n = int(round(dur_h / dt_h))
    return np.cumsum(np.full(n, p_mm / n))


class Perdidas(unittest.TestCase):
    def test_respuesta_conocida(self):          # CN=80: S=63.5 mm, Ia=12.7; P=100 -> Pe=(87.3)²/(87.3+63.5)=50.54
        r = mp.perdidas_scs([100.0], 80)
        self.assertAlmostEqual(r["S_mm"], 63.5, 6); self.assertAlmostEqual(r["Ia_mm"], 12.7, 6)
        self.assertAlmostEqual(r["exceso_acum_mm"][0], 87.3 ** 2 / 150.8, 6)

    def test_impermeable_y_lambda(self):
        p = [100.0]
        base = mp.perdidas_scs(p, 80)["exceso_acum_mm"][0]
        self.assertAlmostEqual(mp.perdidas_scs(p, 80, f_imp=0.3)["exceso_acum_mm"][0], 0.3 * 100 + 0.7 * base, 9)
        self.assertGreater(mp.perdidas_scs(p, 80, lam=0.05)["exceso_acum_mm"][0], base)   # λ menor -> más exceso
        self.assertAlmostEqual(mp.perdidas_scs(p, 80, f_imp=1.0)["exceso_acum_mm"][0], 100.0, 9)

    def test_cn100_y_seco(self):
        self.assertAlmostEqual(mp.perdidas_scs([30.0], 100)["exceso_acum_mm"][0], 30.0, 9)
        r = mp.perdidas_scs([0.0, 0.0], 75)
        self.assertTrue(np.all(r["exceso_acum_mm"] == 0)); self.assertTrue(any("seco" in a for a in r["avisos"]))

    def test_positividad_y_cota(self):
        p = _tormenta(0.1)
        r = mp.perdidas_scs(p, 70, f_imp=0.1)
        self.assertTrue(np.all(r["exceso_inc_mm"] >= 0)); self.assertLessEqual(r["exceso_acum_mm"][-1], p[-1] + 1e-12)
        self.assertAlmostEqual(r["exceso_inc_mm"].sum(), r["exceso_acum_mm"][-1], 9)

    def test_invalidos(self):
        for args in (([10], 0), ([10], 101), ([10], float("nan")), ([-1], 80), ([5, 4], 80), ([float("nan")], 80), ([], 80)):
            with self.assertRaises(ValueError): mp.perdidas_scs(*args)
        for kw in ({"lam": -0.1}, {"lam": 1.5}, {"f_imp": 1.2}, {"f_imp": -0.1}):
            with self.assertRaises(ValueError): mp.perdidas_scs([10], 80, **kw)
        self.assertTrue(mp.perdidas_scs([10], 80, lam=0.5)["avisos"])      # fuera de lo usual: avisa, no corrige


class UnitarioSCS(unittest.TestCase):
    def test_base_y_pico(self):
        a = mp.uh_scs(100.0, 2.0, 0.5, 484)
        self.assertAlmostEqual(a["tb_sobre_tp"], 2.6667, 3)                       # 1290,7/484
        self.assertAlmostEqual(a["qp_m3s_mm"], 0.2083333 * 100 / a["tp_h"], 4)      # conversión exacta de unidades
        b = mp.uh_scs(100.0, 2.0, 0.5, 284)
        self.assertAlmostEqual(b["tb_sobre_tp"], 4.5446, 3); self.assertLess(b["qp_m3s_mm"], a["qp_m3s_mm"])
        self.assertAlmostEqual(a["tp_h"], 2.25, 12)                                # tp = Δt/2 + Lag

    def test_volumen_unitario_exacto(self):
        for prf in (484, 284, 150):
            for dt in (1.0, 0.5, 0.1):
                r = mp.uh_scs(37.5, 1.3, dt, prf)
                self.assertAlmostEqual(r["u_m3s_mm"].sum() * dt * 3600, 1000 * 37.5, 6)
                self.assertTrue(np.all(r["u_m3s_mm"] >= 0))

    def test_convolucion_conserva_volumen(self):
        for prf in (484, 284):
            pe = mp.perdidas_scs(_tormenta(0.25), 78, f_imp=0.05)["exceso_inc_mm"]
            u = mp.uh_scs(52.0, 1.7, 0.25, prf)
            q = mp.convolver(pe, u["u_m3s_mm"], 0.25)
            self.assertAlmostEqual(q["volumen_m3"], pe.sum() * 52.0 * 1000, 4)
            self.assertTrue(np.all(q["q_m3s"] >= 0))

    def test_seco_e_invalidos(self):
        u = mp.uh_scs(10.0, 1.0, 0.5)
        self.assertTrue(np.all(mp.convolver(np.zeros(6), u["u_m3s_mm"], 0.5)["q_m3s"] == 0))
        for args in ((0, 1, 1), (10, 0, 1), (10, 1, 0), (10, 1, 1, 0), (float("nan"), 1, 1), (10, -1, 1)):
            with self.assertRaises(ValueError): mp.uh_scs(*args)
        self.assertTrue(mp.uh_scs(10, 1, 1, 50)["avisos"])

    def test_convergencia_paso(self):
        """Mismo evento (3 h, 90 mm, CN 78) con Δt que se divide a la mitad: el pico varía cada vez menos."""
        picos = []
        for dt in (1.0, 0.5, 0.25, 0.125, 0.0625):
            pe = mp.perdidas_scs(_tormenta(dt), 78)["exceso_inc_mm"]
            q = mp.convolver(pe, mp.uh_scs(52.0, 1.7, dt, 484)["u_m3s_mm"], dt)["q_m3s"]
            picos.append(q.max() / dt * dt)   # pico del hidrograma de respuesta (m³/s)
        # la respuesta a incrementos discretos se escala con Δt (pe por paso); se compara por la intensidad equivalente
        dif = np.abs(np.diff(picos))
        self.assertTrue(np.all(np.diff(dif) < 0), picos)
        self.assertLess(dif[-1] / picos[-1], 0.02)       # tp = Δt/2 + Lag cambia con Δt: el límite existe pero converge lento


class MuskingumCunge(unittest.TestCase):
    PAR = dict(dx_m=3000.0, c_ms=1.0, ancho_m=40.0, s0=0.001)   # con dt=3000 s: C=1, D<=0,67 -> C0,C2>0

    def _entrada(self, dt_s, pico=80.0, dur_h=6.0):
        t = np.arange(0, dur_h * 3600 + dt_s, dt_s)
        return np.where(t < 3600 * dur_h / 2, pico * t / (3600 * dur_h / 2), np.maximum(pico * (1 - (t - 3600 * dur_h / 2) / (3600 * dur_h / 2)), 0))

    def test_coeficientes_suman_uno_y_x(self):
        for c, dt, q in ((1.0, 600, 5), (2.0, 900, 100), (0.5, 60, 0), (3.0, 3600, 300)):
            k = mp.coeficientes_mc(c, dt, 5000, q, 30, 0.002)
            self.assertAlmostEqual(k["C0"] + k["C1"] + k["C2"], 1.0, 12)
            self.assertAlmostEqual(k["X"], 0.5 * (1 - k["D"]), 12); self.assertAlmostEqual(k["K_s"], 5000 / c, 9)
        # equivalencia con la forma clásica K, X
        k = mp.coeficientes_mc(1.2, 900, 6000, 40, 25, 0.001)
        K, X, dt = k["K_s"], k["X"], 900
        den = K * (1 - X) + 0.5 * dt
        self.assertAlmostEqual(k["C0"], (-K * X + 0.5 * dt) / den, 12)
        self.assertAlmostEqual(k["C2"], (K * (1 - X) - 0.5 * dt) / den, 12)

    def test_conservacion_parametros_constantes(self):
        q = self._entrada(3000.0)
        r = mp.muskingum_cunge(q, 3000.0, **self.PAR)
        self.assertEqual(r["n_C0_negativo"], 0); self.assertEqual(r["n_D_limitado"], 0)
        self.assertLess(abs(r["error_balance_rel"]), 1e-9)
        self.assertTrue(np.all(r["q_out_m3s"] >= 0)); self.assertLess(r["q_out_m3s"].max(), q.max())     # atenuación

    def test_seco_e_invalidos(self):
        r = mp.muskingum_cunge(np.zeros(20), 600.0, **self.PAR)
        self.assertTrue(np.all(r["q_out_m3s"] == 0)); self.assertTrue(r["avisos"])
        for kw in ({"dx_m": 0}, {"c_ms": -1}, {"ancho_m": 0}, {"s0": 0}, {"dx_m": float("nan")}):
            with self.assertRaises(ValueError): mp.muskingum_cunge(np.ones(5), 600.0, **{**self.PAR, **kw})
        with self.assertRaises(ValueError): mp.muskingum_cunge([1, -1, 2], 600.0, **self.PAR)
        with self.assertRaises(ValueError): mp.muskingum_cunge([1, float("nan")], 600.0, **self.PAR)
        with self.assertRaises(ValueError): mp.muskingum_cunge(np.ones(3), 0, **self.PAR)

    def test_fuera_de_dominio_se_reporta(self):
        # tramo muy corto y caudal alto: D>1 -> se limita y se avisa; nunca queda salida negativa
        r = mp.muskingum_cunge(self._entrada(600.0, pico=500.0), 600.0, dx_m=500.0, c_ms=1.0, ancho_m=10.0, s0=0.0005)
        self.assertGreater(r["n_D_limitado"], 0); self.assertTrue(any("D>1" in a for a in r["avisos"]))
        self.assertTrue(np.all(r["q_out_m3s"] >= 0))
        d = mp.diagnostico_tramo(1.0, 600, 500, 500, 10, 0.0005)
        self.assertTrue(any("D>1" in b for b in d["banderas"])); self.assertAlmostEqual(d["dx_min_X_no_negativo_m"], 500 / (10 * 0.0005 * 1.0))

    def test_c0_negativo_no_produce_negativos(self):
        r = mp.muskingum_cunge(self._entrada(60.0, pico=1.0), 60.0, dx_m=100000.0, c_ms=1.0, ancho_m=100.0, s0=0.01)
        self.assertGreater(r["n_C0_negativo"], 0); self.assertTrue(np.all(r["q_out_m3s"] >= 0))
        # sin recorte, la conservación con parámetros constantes es exacta aunque C0<0 (pueden aparecer valores negativos)
        r2 = mp.muskingum_cunge(self._entrada(600.0), 600.0, dx_m=10000.0, c_ms=1.5, ancho_m=40.0, s0=0.001, recortar_negativos=False)
        self.assertGreater(r2["n_C0_negativo"], 0); self.assertLess(abs(r2["error_balance_rel"]), 1e-9)

    def test_parametros_variables_estables(self):
        r = mp.muskingum_cunge(self._entrada(600.0), 600.0, dx_m=10000.0, c_ms=lambda q: 1.0 + 0.01 * q, ancho_m=lambda q: 30 + 0.2 * q, s0=0.001)
        self.assertTrue(r["variable"]); self.assertTrue(np.all(r["q_out_m3s"] >= 0))
        self.assertTrue(math.isfinite(r["error_balance_rel"])); self.assertTrue(r["avisos"])   # el balance se REPORTA; no se afirma exacto

    def test_convergencia_paso(self):
        """Δx fijo (10 km, X>=0), Δt a la mitad: el pico de salida deja de cambiar. Con C+D<1 (C0<0) hay una oscilación
        pequeña y no monótona al inicio; se exige que la última diferencia sea menor que la primera y < 0,1 %."""
        picos = [mp.muskingum_cunge(self._entrada(dt), dt, dx_m=10000.0, c_ms=1.5, ancho_m=40.0, s0=0.001)["q_out_m3s"].max()
                 for dt in (3000.0, 1500.0, 750.0, 375.0, 187.5, 93.75)]
        dif = np.abs(np.diff(picos))
        self.assertLess(dif[-1], dif[0]); self.assertLess(dif[-1] / picos[-1], 0.001, picos)


class Courant(unittest.TestCase):
    def test_conocido(self):
        r = mp.dt_courant(10.0, [1.0], [0.0], alfa=0.5)
        self.assertAlmostEqual(r["dt_s"], 0.5 * 10 / math.sqrt(9.80665), 9)
        self.assertAlmostEqual(mp.dt_courant(10.0, [1.0], [2.0], alfa=1.0)["dt_s"], 10 / (2 + math.sqrt(9.80665)), 9)

    def test_secas_y_critica(self):
        r = mp.dt_courant(5.0, [0.0, 0.5, 2.0], [0.0, 0.1, 1.0])
        self.assertEqual(r["celdas_secas"], 1); self.assertEqual(r["celda_critica"], 2)
        s = mp.dt_courant(5.0, [0.0, 0.0], [0.0, 0.0])
        self.assertTrue(math.isinf(s["dt_s"])); self.assertTrue(s["avisos"])

    def test_invalidos_y_monotonia(self):
        for args in ((0, [1], [0]), (5, [-1], [0]), (5, [float("nan")], [0]), (5, [1], [float("inf")])):
            with self.assertRaises(ValueError): mp.dt_courant(*args)
        for a in (0, 1.5):
            with self.assertRaises(ValueError): mp.dt_courant(5, [1], [0], alfa=a)
        self.assertLess(mp.dt_courant(5, [3.0], [0.0])["dt_s"], mp.dt_courant(5, [1.0], [0.0])["dt_s"])   # más profundo -> paso menor
        self.assertLess(mp.dt_courant(2, [1.0], [0.0])["dt_s"], mp.dt_courant(5, [1.0], [0.0])["dt_s"])   # malla más fina -> paso menor


if __name__ == "__main__":
    unittest.main()
