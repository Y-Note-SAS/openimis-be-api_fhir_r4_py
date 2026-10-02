import unittest
from types import SimpleNamespace

from django.apps import apps
from django.test import TestCase

from api_fhir_r4.converters.coverageConverter import CoverageConverter
from api_fhir_r4.models import CoverageV2 as Coverage


@unittest.skipUnless(apps.is_installed('program'), 'CSU only: program module is not installed')
class CoverageConverterCsuTests(TestCase):
    """CSU: program class and Chèque Santé voucher exposed on Coverage."""

    @staticmethod
    def _empty_coverage():
        coverage = Coverage.construct(status='active')
        coverage.identifier = []
        coverage.class_fhir = []
        coverage.extension = []
        return coverage

    @staticmethod
    def _policy(program_name, program_code, policy_number='100001', cheque_status=None):
        program = SimpleNamespace(idProgram=4, code=program_code, nameProgram=program_name)
        product = SimpleNamespace(program=program)
        return SimpleNamespace(
            product=product,
            policy_number=policy_number,
            csu_cheque_status=cheque_status,
        )

    def test_program_is_exposed_as_an_extra_class(self):
        coverage = self._empty_coverage()

        CoverageConverter.build_csu_program_and_cheque(
            coverage, self._policy('Chêque Santé', 'CCS')
        )

        program_class = coverage.class_fhir[-1]
        self.assertEqual('CCS', program_class.value)
        self.assertEqual('Chêque Santé', program_class.name)
        self.assertEqual('program', program_class.type.coding[0].code)

    def test_program_without_program_is_ignored(self):
        coverage = self._empty_coverage()
        policy = self._policy('Chêque Santé', 'CCS')
        policy.product.program = None

        CoverageConverter.build_csu_program_and_cheque(coverage, policy)

        self.assertEqual([], coverage.class_fhir)
        self.assertEqual([], coverage.identifier)
        self.assertEqual([], coverage.extension)

    def test_cheque_number_and_status_are_exposed_for_cheque_sante(self):
        coverage = self._empty_coverage()

        CoverageConverter.build_csu_program_and_cheque(
            coverage, self._policy('Chêque Santé', 'CCS', cheque_status='Used')
        )

        identifiers = {i.type.coding[0].code: i.value for i in coverage.identifier}
        self.assertEqual('100001', identifiers['cheque-sante'])
        extensions = {e.url.split('/')[-1]: e.valueCode for e in coverage.extension}
        self.assertEqual('Used', extensions['cheque-status'])

    def test_cheque_is_not_exposed_for_another_program(self):
        coverage = self._empty_coverage()

        CoverageConverter.build_csu_program_and_cheque(
            coverage, self._policy('Gratuité (enfant - de 5 ans)', 'GRAT', cheque_status='Used')
        )

        codes = [i.type.coding[0].code for i in coverage.identifier]
        self.assertNotIn('cheque-sante', codes)
        self.assertEqual([], coverage.extension)

    def test_cheque_number_is_not_exposed_without_policy_number(self):
        coverage = self._empty_coverage()

        CoverageConverter.build_csu_program_and_cheque(
            coverage, self._policy('Chêque Santé', 'CCS', policy_number=None, cheque_status='Used')
        )

        codes = [i.type.coding[0].code for i in coverage.identifier]
        self.assertNotIn('cheque-sante', codes)
