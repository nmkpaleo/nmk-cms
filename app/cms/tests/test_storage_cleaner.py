from django.test import SimpleTestCase

from cms.storage_cleaner import normalize_storage_area, normalize_storage_token


class StorageCleanerTests(SimpleTestCase):
    def test_normalizes_letter_first_values(self):
        self.assertEqual(normalize_storage_token("AA11"), "AA 11")
        self.assertEqual(normalize_storage_token("AA 1/1"), "AA 11")

    def test_normalizes_number_first_values(self):
        self.assertEqual(normalize_storage_token("08AF"), "08 AF")
        self.assertEqual(normalize_storage_token("08 AF"), "08 AF")
        self.assertEqual(normalize_storage_token("81 G/F"), "81 GF")
        self.assertEqual(normalize_storage_token("35 AB"), "35 AB")
        self.assertIsNone(normalize_storage_token("123 ABC"))

    def test_deduplicates_pipe_delimited_values(self):
        self.assertEqual(normalize_storage_area("08AF | 08 AF"), "08 AF")
