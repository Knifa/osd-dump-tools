import unittest

from osd.utils.ro_cls import read_only_class


class TestReadOnly(unittest.TestCase):
    def test_exception_cls_attr_on_modify(self):

        @read_only_class
        class A:
            a = 0

        a = A()
        with self.assertRaises(AttributeError):
            a.a = 1
