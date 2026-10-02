import unittest

from django.apps import apps
from django.test import TestCase
from django.urls import resolve

from api_fhir_r4.converters.planDefinitionConverter import PlanDefinitionConverter
from api_fhir_r4.views.fhir.plan_definition import PlanDefinitionViewSet


@unittest.skipUnless(apps.is_installed('program'), 'CSU only: program module is not installed')
class PlanDefinitionConverterCsuTests(TestCase):
    """CSU: openIMIS Program exposed as a read-only FHIR R4 PlanDefinition."""

    def setUp(self):
        from program.models import Program
        self.program = Program(idProgram=99, code='CCS', nameProgram='Chêque Santé')

    def test_to_fhir_obj_maps_program_fields(self):
        fhir_plan_definition = PlanDefinitionConverter.to_fhir_obj(self.program)

        self.assertEqual('PlanDefinition', fhir_plan_definition.resourceType)
        self.assertEqual('99', fhir_plan_definition.id)
        self.assertEqual('Chêque Santé', fhir_plan_definition.name)
        self.assertEqual('Chêque Santé', fhir_plan_definition.title)
        self.assertEqual('active', fhir_plan_definition.status)

        identifiers = {
            identifier.type.coding[0].code: identifier.value
            for identifier in fhir_plan_definition.identifier
        }
        self.assertEqual('99', identifiers['ACSN'])
        self.assertEqual('CCS', identifiers['program-code'])

    def test_to_fhir_obj_handles_missing_program_code(self):
        self.program.code = None

        fhir_plan_definition = PlanDefinitionConverter.to_fhir_obj(self.program)

        codes = [
            identifier.type.coding[0].code
            for identifier in (fhir_plan_definition.identifier or [])
        ]
        self.assertNotIn('program-code', codes)

    def test_to_imis_obj_is_read_only(self):
        with self.assertRaises(NotImplementedError):
            PlanDefinitionConverter.to_imis_obj({}, 1)


@unittest.skipUnless(apps.is_installed('program'), 'CSU only: program module is not installed')
class PlanDefinitionViewSetCsuTests(TestCase):
    def test_plan_definition_route_is_registered(self):
        match = resolve('/api/api_fhir_r4/PlanDefinition/')
        self.assertIsNotNone(match)

    def test_queryset_is_ordered_by_program_id(self):
        queryset = PlanDefinitionViewSet().get_queryset()
        self.assertEqual(['idProgram'], queryset.query.order_by)
