from django.test import SimpleTestCase

from hydro.services.statistics import mann_kendall, percentile_rank, sen_slope, trend_summary


class StatisticsTests(SimpleTestCase):
    def test_percentile_rank(self):
        self.assertAlmostEqual(percentile_rank([1, 2, 3, 4], 2), 50.0)
        self.assertAlmostEqual(percentile_rank([1, 2, 3, 4], 4), 100.0)
        self.assertIsNone(percentile_rank([], 2))

    def test_sen_slope_monotone(self):
        self.assertAlmostEqual(sen_slope([(1, 1), (2, 2), (3, 3), (4, 4)]), 1.0)

    def test_mann_kendall_monotone(self):
        result = mann_kendall([(year, year) for year in range(1, 11)])
        self.assertGreater(result["s"], 0)
        self.assertLess(result["p"], 0.05)
        self.assertTrue(result["significant"])

    def test_mann_kendall_flat_is_neutral(self):
        result = mann_kendall([(year, 50.0) for year in range(1, 11)])
        self.assertEqual(result["s"], 0)
        self.assertEqual(result["p"], 1.0)
        self.assertFalse(result["significant"])

    def test_mann_kendall_short_series_is_guarded(self):
        result = mann_kendall([(1, 1), (2, 2), (3, 3)])
        self.assertEqual(result["n"], 3)
        self.assertIsNone(result["p"])
        self.assertFalse(result["significant"])

    def test_trend_summary_flat(self):
        result = trend_summary([(year, 50.0) for year in range(2016, 2026)], divisor=100.0)
        self.assertEqual(result["score"], 50.0)
        self.assertEqual(result["slope_pct_per_year"], 0.0)

    def test_trend_summary_decline_is_below_neutral(self):
        result = trend_summary(
            [(year, 70 - (year - 2016) * 2) for year in range(2016, 2026)], divisor=100.0
        )
        self.assertLess(result["score"], 50.0)
        self.assertLess(result["slope_pct_per_year"], 0)
