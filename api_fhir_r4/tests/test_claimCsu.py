import unittest

from django.apps import apps
from django.test import TestCase
from fhir.resources.R4B.claim import Claim as FHIRClaim
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.reference import Reference

from claim.models import Claim
from api_fhir_r4.configurations import GeneralConfiguration
from api_fhir_r4.converters.claimConverter import ClaimConverter


@unittest.skipUnless(apps.is_installed('program'), 'CSU only: program module is not installed')
class ClaimConverterCsuProgramTests(TestCase):
    """CSU: the claim program is carried as a PlanDefinition reference extension."""

    def setUp(self):
        from program.models import Program
        self.program = Program.objects.create(code='CCS', nameProgram='Chêque Santé')

    @staticmethod
    def _fhir_claim_with_program_extension(program_id):
        fhir_claim = FHIRClaim.construct(status='active', use='claim', created='2023-01-01')
        extension = Extension.construct()
        extension.url = (
            f'{GeneralConfiguration.get_system_base_url()}/StructureDefinition/claim-program'
        )
        reference = Reference.construct()
        reference.reference = f'PlanDefinition/{program_id}'
        extension.valueReference = reference
        fhir_claim.extension = [extension]
        return fhir_claim

    def test_build_fhir_csu_program_exposes_plan_definition_reference(self):
        fhir_claim = FHIRClaim.construct(status='active', use='claim', created='2023-01-01')
        imis_claim = Claim()
        imis_claim.program = self.program

        ClaimConverter.build_fhir_csu_program(fhir_claim, imis_claim)

        extensions = {
            extension.url.split('/')[-1]: extension.valueReference
            for extension in fhir_claim.extension
        }
        self.assertEqual(
            f'PlanDefinition/{self.program.idProgram}',
            extensions['claim-program'].reference
        )
        self.assertEqual('Chêque Santé', extensions['claim-program'].display)

    def test_build_fhir_csu_program_is_skipped_without_program(self):
        fhir_claim = FHIRClaim.construct(status='active', use='claim', created='2023-01-01')

        ClaimConverter.build_fhir_csu_program(fhir_claim, Claim())

        self.assertFalse(fhir_claim.extension)

    def test_build_imis_csu_program_resolves_the_reference(self):
        fhir_claim = self._fhir_claim_with_program_extension(self.program.idProgram)
        imis_claim = Claim()
        errors = []

        ClaimConverter.build_imis_csu_program(imis_claim, fhir_claim, errors)

        self.assertEqual([], errors)
        self.assertEqual(self.program.idProgram, imis_claim.program.idProgram)

    def test_build_imis_csu_program_reports_an_invalid_reference(self):
        fhir_claim = self._fhir_claim_with_program_extension(999999)
        imis_claim = Claim()
        errors = []

        ClaimConverter.build_imis_csu_program(imis_claim, fhir_claim, errors)

        self.assertEqual(1, len(errors))
        self.assertIsNone(imis_claim.program)

    def test_build_imis_csu_program_is_skipped_without_extension(self):
        imis_claim = Claim()
        errors = []

        ClaimConverter.build_imis_csu_program(imis_claim, FHIRClaim.construct(status='active', use='claim', created='2023-01-01'), errors)

        self.assertEqual([], errors)
        self.assertIsNone(imis_claim.program)
