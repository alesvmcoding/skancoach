import unittest
from xp_calculator import calculate_raw_xp

class RawXpPercentageTests(unittest.TestCase):
    def test_percentages_are_normalized_to_raw(self):
        cases = {
            'MS 20kk/h (300%)': 6_666_667,
            'EK 17.3kkh 375%': 4_613_333,
            'RP XP 9kk 250% profit 2kk': 3_600_000,
            'ED 8kk/h 150%': 5_333_333,
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                result = calculate_raw_xp(title)
                self.assertEqual(result.status, 'calculated')
                self.assertEqual(result.raw_value, expected)

    def test_percent_embedded_in_larger_word_is_ignored(self):
        result = calculate_raw_xp('MS 20kk/h x300percent')
        self.assertEqual(result.status, 'assumed_150')

if __name__ == '__main__':
    unittest.main()
