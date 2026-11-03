import datetime
from types import SimpleNamespace
from unittest import mock

from django.core.exceptions import ObjectDoesNotExist
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.test import APITestCase

from api_fhir_r4.configurations import GeneralConfiguration
from api_fhir_r4.converters.programOrganisationConverter import ProgramOrganisationConverter
from api_fhir_r4.mapping.programMapping import ProgramMapping
from api_fhir_r4.model_retrievers import ProgramIdentifierModelRetriever
from api_fhir_r4.serializers import ProgramOrganisationSerializer
from api_fhir_r4.views.fhir.organisation import OrganisationViewSet


def build_program(id_program=7, code='CCS', name='Cheque Sante', start=None, end=None):
    return SimpleNamespace(
        idProgram=id_program,
        code=code,
        nameProgram=name,
        validityDateFrom=start,
        validityDateTo=end,
    )


class ProgramMappingTestCase(SimpleTestCase):

    def test_fhir_id_has_a_prefix(self):
        self.assertEqual(ProgramMapping.to_fhir_id(build_program(12)), 'program-12')

    def test_from_fhir_id(self):
        self.assertEqual(ProgramMapping.from_fhir_id('program-12'), 12)

    def test_from_fhir_id_rejects_other_identifiers(self):
        for value in ('12', 'program-', 'program-x', 'CCS', '6d0eea8c-62eb-11ea-94d6-c36229a16c2f', None):
            self.assertIsNone(ProgramMapping.from_fhir_id(value), value)

    def test_cheque_sante_is_detected_by_code_only(self):
        self.assertTrue(ProgramMapping.is_cheque_sante(build_program(code='CCS', name='Autre')))
        self.assertFalse(ProgramMapping.is_cheque_sante(build_program(code='OTH', name='Chèque Santé')))
        self.assertFalse(ProgramMapping.is_cheque_sante(build_program(code=None)))
        self.assertFalse(ProgramMapping.is_cheque_sante(None))


class ProgramIdentifierModelRetrieverTestCase(SimpleTestCase):

    def test_validator_only_accepts_program_ids(self):
        self.assertTrue(ProgramIdentifierModelRetriever.identifier_validator('program-3'))
        self.assertFalse(ProgramIdentifierModelRetriever.identifier_validator('3'))
        self.assertFalse(ProgramIdentifierModelRetriever.identifier_validator('CCS'))

    def test_get_model_object_uses_the_technical_id(self):
        queryset = mock.MagicMock()
        ProgramIdentifierModelRetriever.get_model_object(queryset, 'program-3')
        queryset.get.assert_called_once_with(idProgram=3)


class ProgramOrganisationConverterTestCase(SimpleTestCase):

    def test_to_fhir_obj(self):
        program = build_program(
            start=datetime.datetime(2024, 1, 1), end=datetime.datetime(2024, 12, 31, 23, 59))
        fhir = ProgramOrganisationConverter.to_fhir_obj(program).dict()

        self.assertEqual(fhir['resourceType'], 'Organization')
        self.assertEqual(fhir['id'], 'program-7')
        self.assertEqual(fhir['name'], 'Cheque Sante')
        self.assertEqual(fhir['type'][0]['coding'][0]['code'], 'pay')
        self.assertEqual(len(fhir['identifier']), 1)
        self.assertEqual(fhir['identifier'][0]['value'], 'CCS')
        self.assertEqual(fhir['identifier'][0]['system'], ProgramMapping.program_code_system())
        extension = fhir['extension'][0]
        self.assertEqual(extension['url'], ProgramMapping.validity_extension_url())
        self.assertEqual(extension['valuePeriod']['start'], datetime.datetime(2024, 1, 1))
        self.assertEqual(extension['valuePeriod']['end'], datetime.datetime(2024, 12, 31, 23, 59))

    def test_program_without_code_has_no_identifier(self):
        fhir = ProgramOrganisationConverter.to_fhir_obj(build_program(code=None)).dict()
        self.assertEqual(fhir['id'], 'program-7')
        self.assertFalse(fhir.get('identifier'))

    def test_program_without_validity_has_no_extension(self):
        fhir = ProgramOrganisationConverter.to_fhir_obj(build_program()).dict()
        self.assertFalse(fhir.get('extension'))

    def test_program_with_open_ended_validity(self):
        fhir = ProgramOrganisationConverter.to_fhir_obj(
            build_program(start=datetime.datetime(2024, 1, 1))).dict()
        period = fhir['extension'][0]['valuePeriod']
        self.assertEqual(period['start'], datetime.datetime(2024, 1, 1))
        self.assertIsNone(period.get('end'))

    def test_to_imis_obj_is_refused(self):
        with self.assertRaises(MethodNotAllowed):
            ProgramOrganisationConverter.to_imis_obj({}, 1)


class OrganisationViewSetProgramTestCase(SimpleTestCase):

    @staticmethod
    def _request(method, query=None, body=None):
        return SimpleNamespace(method=method, GET=query or {}, data=body or {})

    def _is_eligible(self, method, query=None, body=None):
        context = {'request': self._request(method, query, body)}
        return OrganisationViewSet._program_serializer_validator(context)

    @staticmethod
    def _body(organisation_type):
        return {'type': [{'coding': [{'code': organisation_type}]}]}

    def test_get_is_eligible_for_pay_or_untyped_requests(self):
        self.assertTrue(self._is_eligible('GET', {'type': 'pay'}))
        self.assertTrue(self._is_eligible('GET'))
        for other in ('prov', 'bus', 'ins'):
            self.assertFalse(self._is_eligible('GET', {'type': other}), other)

    def test_write_is_only_eligible_for_pay(self):
        self.assertTrue(self._is_eligible('POST', body=self._body('pay')))
        self.assertTrue(self._is_eligible('PUT', body=self._body('pay')))
        self.assertFalse(self._is_eligible('POST', body=self._body('prov')))
        self.assertFalse(self._is_eligible('PUT', body=self._body('bus')))
        # an untyped PUT keeps targeting the existing types only
        self.assertFalse(self._is_eligible('PUT'))

    def test_existing_validators_do_not_target_pay(self):
        for validator in (OrganisationViewSet._hf_serializer_validator,
                          OrganisationViewSet._ph_serializer_validator,
                          OrganisationViewSet._io_serializer_validator):
            self.assertFalse(validator({'request': self._request('GET', {'type': 'pay'})}))
            self.assertFalse(validator({'request': self._request('POST', body=self._body('pay'))}))

    def test_serializers_without_program_module(self):
        view = OrganisationViewSet()
        view.request = self._request('GET')
        with mock.patch.object(OrganisationViewSet, '_is_program_module_installed', return_value=False), \
                mock.patch.object(OrganisationViewSet, '_hf_queryset'), \
                mock.patch.object(OrganisationViewSet, '_ph_queryset'), \
                mock.patch.object(OrganisationViewSet, '_io_queryset'):
            self.assertEqual(len(view.serializers), 3)
            self.assertNotIn(ProgramOrganisationSerializer, view.serializers)

    def test_serializers_with_program_module(self):
        view = OrganisationViewSet()
        view.request = self._request('GET')
        with mock.patch.object(OrganisationViewSet, '_is_program_module_installed', return_value=True), \
                mock.patch.object(OrganisationViewSet, '_hf_queryset'), \
                mock.patch.object(OrganisationViewSet, '_ph_queryset'), \
                mock.patch.object(OrganisationViewSet, '_io_queryset'), \
                mock.patch.object(OrganisationViewSet, '_program_queryset'):
            self.assertEqual(len(view.serializers), 4)
            self.assertIn(ProgramOrganisationSerializer, view.serializers)

    def _program_queryset(self, found=None):
        queryset = mock.MagicMock()
        queryset.model._meta.label = 'program.Program'
        queryset.get.side_effect = (lambda **kw: found) if found else ObjectDoesNotExist
        return queryset

    def test_program_id_is_resolved_by_the_program_retriever_only(self):
        view = OrganisationViewSet()
        view.request = self._request('GET')
        view.check_object_permissions = mock.MagicMock()
        program = build_program(3)
        ref_type, instance = view._get_object_with_first_valid_retriever(
            self._program_queryset(program), 'program-3')
        self.assertIs(instance, program)
        self.assertEqual(ref_type, ProgramIdentifierModelRetriever.serializer_reference_type)

    def test_unknown_program_id(self):
        view = OrganisationViewSet()
        view.request = self._request('GET')
        view.check_object_permissions = mock.MagicMock()
        self.assertEqual(
            view._get_object_with_first_valid_retriever(self._program_queryset(), 'program-3'), (None, None))

    def test_other_identifiers_are_never_looked_up_in_programs(self):
        # a numeric id (health facility) or a code must not be ambiguous with a program
        view = OrganisationViewSet()
        for identifier in ('3', 'CCS', '6d0eea8c-62eb-11ea-94d6-c36229a16c2f'):
            queryset = self._program_queryset(build_program(3))
            self.assertEqual(view._get_object_with_first_valid_retriever(queryset, identifier), (None, None))
            queryset.get.assert_not_called()

    def test_program_id_is_never_looked_up_in_other_types(self):
        view = OrganisationViewSet()
        queryset = mock.MagicMock()
        queryset.model._meta.label = 'location.HealthFacility'
        self.assertEqual(view._get_object_with_first_valid_retriever(queryset, 'program-3'), (None, None))
        queryset.get.assert_not_called()


class ProgramOrganisationAPITests(APITestCase):
    """Needs the full openIMIS stack and the program module."""
    base_url = GeneralConfiguration.get_base_url() + 'Organization/'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from core.test_helpers import create_test_interactive_user
        from graphql_jwt.shortcuts import get_token
        from program.test_helpers import create_test_program
        from api_fhir_r4.tests.test_api_organisation import DummyContext

        cls.program = create_test_program(code='CCS', name='Cheque Sante Org Test')
        cls.program_without_code = create_test_program(code=None, name='Program without code')
        cls.admin_user = create_test_interactive_user(username='testProgramOrgAdmin')
        cls.headers = {
            'Content-Type': 'application/json',
            'HTTP_AUTHORIZATION': f'Bearer {get_token(cls.admin_user, DummyContext(user=cls.admin_user))}',
        }

    def _get(self, suffix=''):
        return self.client.get(self.base_url + suffix, format='json', **self.headers)

    def _types(self, response):
        return {
            entry['resource']['type'][0]['coding'][0]['code']
            for entry in response.json().get('entry', [])
            if entry['resource'].get('type')
        }

    def test_list_type_pay(self):
        response = self._get('?type=pay')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {entry['resource']['id'] for entry in response.json()['entry']}
        self.assertIn(f'program-{self.program.idProgram}', ids)
        self.assertIn(f'program-{self.program_without_code.idProgram}', ids)
        self.assertEqual(self._types(response), {'pay'})

    def test_list_without_type_includes_programs(self):
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('pay', self._types(response))

    def test_other_types_do_not_include_programs(self):
        for organisation_type in ('prov', 'bus', 'ins'):
            response = self._get(f'?type={organisation_type}')
            self.assertEqual(response.status_code, status.HTTP_200_OK, organisation_type)
            self.assertNotIn('pay', self._types(response), organisation_type)

    def test_retrieve(self):
        response = self._get(f'program-{self.program.idProgram}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['id'], f'program-{self.program.idProgram}')
        self.assertEqual(body['name'], 'Cheque Sante Org Test')
        self.assertEqual(body['identifier'][0]['value'], 'CCS')

    def test_retrieve_program_without_code(self):
        response = self._get(f'program-{self.program_without_code.idProgram}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_unknown_program(self):
        self.assertEqual(self._get('program-99999999/').status_code, status.HTTP_404_NOT_FOUND)

    def test_numeric_id_is_not_resolved_as_a_program(self):
        # a bare numeric id must never be ambiguous between a health facility and a program
        response = self._get(f'{self.program.idProgram}/')
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND))
        if response.status_code == status.HTTP_200_OK:
            self.assertNotEqual(response.json()['type'][0]['coding'][0]['code'], 'pay')

    def test_write_is_refused(self):
        body = {
            'resourceType': 'Organization',
            'type': [{'coding': [{'code': 'pay'}]}],
            'name': 'New program',
        }
        response = self.client.post(self.base_url, data=body, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.put(
            self.base_url + f'program-{self.program.idProgram}/', data=body, format='json', **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
