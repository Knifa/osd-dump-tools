import unittest

from osd.config import ExcludeArea

class TestExcludeArea(unittest.TestCase):
    def test_point_in_area(self):
        area = ExcludeArea('1, 1, 3, 3')
        self.assertTrue(area.is_excluded(2, 2))
        self.assertFalse(area.is_excluded(5, 5))

    def test_wrong_input(self):
        with self.assertRaises(ValueError):
            area = ExcludeArea('1, 1, 3')

        with self.assertRaises(ValueError):
            area = ExcludeArea('1, 1, 3, a')

    def test_empty_input(self):
        area = ExcludeArea()
        self.assertEqual(area.x1, -1)
    
