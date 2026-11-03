import sys
from types import ModuleType, SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from api_fhir_r4.configurations import GeneralConfiguration
from api_fhir_r4.converters.claimConverter import ClaimConverter
from api_fhir_r4.exceptions import FHIRRequestProcessException
from api_fhir_r4.mapping.programMapping import ProgramMapping
from api_fhir_r4.tests.test_api_claim import ClaimAPITests
from api_fhir_r4.tests.utils import load_and_replace_json, get_connection_payload
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.reference import Reference


def fake_program_module(programs):
    """programs: Program stand-ins, looked up by idProgram."""
    manager = mock.MagicMock()
    manager.filter.side_effect = lambda idProgram: SimpleNamespace(
        first=lambda: next((p for p in programs if p.idProgram == idProgram), None))
    module = ModuleType('program.models')
    module.Program = SimpleNamespace(objects=manager)
    package = ModuleType('program')
    package.models = module
    return {'program': package, 'program.models': module}


def program_extension(reference='Organization/program-7'):
    extension = Extension.construct()
    extension.url = ProgramMapping.claim_program_extension_url()
    value = Reference.construct()
    value.reference = reference
    extension.valueReference = value
    return extension


def fhir_claim_with(extensions):
    return SimpleNamespace(extension=extensions)


class ClaimProgramConverterTestCase(SimpleTestCase):
    program = SimpleNamespace(idProgram=7, code='CCS', nameProgram='Cheque Sante')

    def test_to_fhir_exposes_the_program(self):
        fhir_claim = SimpleNamespace(extension=None)
        ClaimConverter.build_fhir_csu_program(fhir_claim, SimpleNamespace(program=self.program))
        extension = fhir_claim.extension[0]
        self.assertEqual(extension.url, ProgramMapping.claim_program_extension_url())
        self.assertEqual(extension.valueReference.reference, 'Organization/program-7')
        self.assertEqual(extension.valueReference.display, 'Cheque Sante')

    def test_to_fhir_keeps_existing_extensions(self):
        fhir_claim = SimpleNamespace(extension=[mock.sentinel.other])
        ClaimConverter.build_fhir_csu_program(fhir_claim, SimpleNamespace(program=self.program))
        self.assertEqual(len(fhir_claim.extension), 2)

    def test_to_fhir_without_program(self):
        for imis_claim in (SimpleNamespace(program=None), SimpleNamespace()):
            fhir_claim = SimpleNamespace(extension=None)
            ClaimConverter.build_fhir_csu_program(fhir_claim, imis_claim)
            self.assertIsNone(fhir_claim.extension)

    def test_to_imis_sets_the_program(self):
        imis_claim, errors = SimpleNamespace(), []
        with mock.patch.dict(sys.modules, fake_program_module([self.program])):
            ClaimConverter.build_imis_csu_program(
                imis_claim, fhir_claim_with([program_extension()]), errors)
        self.assertEqual(errors, [])
        self.assertIs(imis_claim.program, self.program)

    def test_to_imis_unknown_program(self):
        imis_claim, errors = SimpleNamespace(), []
        with mock.patch.dict(sys.modules, fake_program_module([self.program])):
            ClaimConverter.build_imis_csu_program(
                imis_claim, fhir_claim_with([program_extension('Organization/program-99')]), errors)
        self.assertEqual(len(errors), 1)
        self.assertFalse(hasattr(imis_claim, 'program'))

    def test_to_imis_rejects_a_reference_that_is_not_a_program_id(self):
        for reference in ('Organization/7', 'Organization/CCS', 'PlanDefinition/7'):
            imis_claim, errors = SimpleNamespace(), []
            with mock.patch.dict(sys.modules, fake_program_module([self.program])):
                ClaimConverter.build_imis_csu_program(
                    imis_claim, fhir_claim_with([program_extension(reference)]), errors)
            self.assertEqual(len(errors), 1, reference)

    def test_to_imis_extension_without_reference(self):
        imis_claim, errors = SimpleNamespace(), []
        extension = program_extension()
        extension.valueReference = None
        ClaimConverter.build_imis_csu_program(imis_claim, fhir_claim_with([extension]), errors)
        self.assertEqual(len(errors), 1)

    def test_to_imis_program_module_not_installed(self):
        imis_claim, errors = SimpleNamespace(), []
        with mock.patch.dict(sys.modules, {'program': None, 'program.models': None}):
            ClaimConverter.build_imis_csu_program(
                imis_claim, fhir_claim_with([program_extension()]), errors)
        self.assertEqual(len(errors), 1)
        self.assertFalse(hasattr(imis_claim, 'program'))

    def test_to_imis_without_extension_is_not_an_error(self):
        for extensions in (None, [], [Extension.construct(url='http://other')]):
            imis_claim, errors = SimpleNamespace(), []
            ClaimConverter.build_imis_csu_program(imis_claim, fhir_claim_with(extensions), errors)
            self.assertEqual(errors, [])
            self.assertFalse(hasattr(imis_claim, 'program'))

    def test_errors_are_reported_as_request_errors(self):
        with self.assertRaises(FHIRRequestProcessException):
            ClaimConverter.check_errors(['Invalid `program` reference'])


class ClaimProgramAPITests(ClaimAPITests):
    """
    Needs the full openIMIS stack and the program module.

    Checks that the program is actually persisted in claim.program, not only converted.
    """
    # the inherited tests are already run by ClaimAPITests
    test_post_should_create_correctly = None
    test_get_should_return_200_claim_response = None
    test_get_should_required_login = None

    def setUp(self):
        super().setUp()
        from program.test_helpers import create_test_program
        self.program = create_test_program(code='CCS', name='Cheque Sante Claim Test')

    def _login_headers(self):
        response = self.client.post(
            GeneralConfiguration.get_base_url() + 'login/',
            data=get_connection_payload(self._TEST_DATA_USER), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {'Content-Type': 'application/json', 'HTTP_AUTHORIZATION': f"Bearer {response.json()['token']}"}

    def _claim_payload(self, code, program_reference=None):
        data = load_and_replace_json(self._test_json_path, self.sub_str)
        data['identifier'][0]['value'] = code
        if program_reference:
            data['extension'] = [{
                'url': ProgramMapping.claim_program_extension_url(),
                'valueReference': {'reference': program_reference},
            }]
        return data

    def _post(self, data):
        return self.client.post(self.base_url, data=data, format='json', **self._login_headers())

    def test_post_persists_the_program(self):
        from claim.models import Claim
        response = self._post(self._claim_payload('T-CSU-01', f'Organization/program-{self.program.idProgram}'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        claim = Claim.objects.get(code='T-CSU-01', validity_to__isnull=True)
        self.assertEqual(claim.program_id, self.program.idProgram)

    def test_post_without_extension_leaves_the_program_empty(self):
        from claim.models import Claim
        response = self._post(self._claim_payload('T-CSU-02'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertIsNone(Claim.objects.get(code='T-CSU-02', validity_to__isnull=True).program_id)

    def test_post_with_unknown_program_is_refused(self):
        from claim.models import Claim
        response = self._post(self._claim_payload('T-CSU-03', 'Organization/program-99999999'))
        self.assertGreaterEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertLess(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertFalse(Claim.objects.filter(code='T-CSU-03').exists())

    def test_get_exposes_the_program(self):
        from claim.models import Claim
        self.assertEqual(
            self._post(self._claim_payload('T-CSU-04', f'Organization/program-{self.program.idProgram}'))
            .status_code, status.HTTP_201_CREATED)
        claim = Claim.objects.get(code='T-CSU-04', validity_to__isnull=True)
        response = self.client.get(f'{self.base_url}{claim.uuid}/', format='json', **self._login_headers())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        references = [
            e['valueReference']['reference'] for e in response.json().get('extension', [])
            if e['url'] == ProgramMapping.claim_program_extension_url()
        ]
        self.assertEqual(references, [f'Organization/program-{self.program.idProgram}'])
