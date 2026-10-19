import sys
from types import ModuleType, SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from api_fhir_r4.converters.coverageConverter import CoverageConverter
from api_fhir_r4.mapping.programMapping import ProgramMapping
from api_fhir_r4.models import CoverageV2 as Coverage
from api_fhir_r4.views.fhir.coverage_request import CoverageRequestQuerySet
from fhir.resources.R4B.reference import Reference


def build_program(id_program=7, code='CCS', name='Cheque Sante'):
    return SimpleNamespace(idProgram=id_program, code=code, nameProgram=name)


def build_policy(program, policy_number='ABC123', **attrs):
    return SimpleNamespace(product=SimpleNamespace(program=program), policy_number=policy_number, **attrs)


def build_coverage():
    # CoverageV2 validates the whole resource on every assignment: mandatory elements first.
    coverage = Coverage.construct()
    coverage.status = 'active'
    beneficiary = Reference.construct()
    beneficiary.reference = 'Patient/CHF1'
    coverage.beneficiary = beneficiary
    payor = Reference.construct()
    payor.reference = 'Patient/CHF1'
    coverage.payor = [payor]
    return coverage


def fake_cs_module(statuses):
    """statuses: list of (code, status), in registry order."""
    manager = mock.MagicMock()

    def filter_(**kwargs):
        lines = list(statuses)
        if 'chequeImportLineCode' in kwargs:
            lines = [line for line in lines if line[0] == kwargs['chequeImportLineCode']]
        if 'chequeImportLineCode__in' in kwargs:
            lines = [line for line in lines if line[0] in kwargs['chequeImportLineCode__in']]
        queryset = mock.MagicMock()
        queryset.order_by.return_value = queryset
        queryset.values_list.return_value = lines
        queryset.first.return_value = SimpleNamespace(
            chequeImportLineStatus=lines[-1][1]) if lines else None
        return queryset

    manager.filter.side_effect = filter_
    module = ModuleType('cs.models')
    module.ChequeImportLine = SimpleNamespace(objects=manager)
    package = ModuleType('cs')
    package.models = module
    return {'cs': package, 'cs.models': module}


class CoverageCsuTestCase(SimpleTestCase):

    def _extension_values(self, coverage, url):
        return [e.valueCode for e in coverage.extension or [] if e.url == url]

    def test_program_is_appended_to_payor(self):
        coverage = build_coverage()
        CoverageConverter.build_csu_program(coverage, build_policy(build_program(code='OTH')))
        self.assertEqual([p.reference for p in coverage.payor], ['Patient/CHF1', 'Organization/program-7'])

    def test_policy_without_program(self):
        coverage = build_coverage()
        CoverageConverter.build_csu_program(coverage, build_policy(None))
        self.assertEqual([p.reference for p in coverage.payor], ['Patient/CHF1'])
        self.assertFalse(coverage.extension)

    def test_product_without_program_attribute(self):
        # instance without the program module: Product has no `program`
        coverage = build_coverage()
        policy = SimpleNamespace(product=SimpleNamespace(), policy_number='ABC123')
        CoverageConverter.build_csu_program(coverage, policy)
        self.assertEqual(len(coverage.payor), 1)

    def test_program_without_code(self):
        coverage = build_coverage()
        CoverageConverter.build_csu_program(coverage, build_policy(build_program(code=None)))
        self.assertEqual(len(coverage.payor), 2)
        self.assertFalse(coverage.extension)
        self.assertFalse(coverage.identifier)

    def test_cheque_sante_identifier_and_status(self):
        coverage = build_coverage()
        with mock.patch.dict(sys.modules, fake_cs_module([('ABC123', 'New'), ('ABC123', 'Used')])):
            CoverageConverter.build_csu_program(coverage, build_policy(build_program()))
        self.assertEqual(coverage.identifier[0].value, 'ABC123')
        self.assertEqual(coverage.identifier[0].system, ProgramMapping.cheque_sante_system())
        # the latest registry entry wins
        self.assertEqual(self._extension_values(coverage, ProgramMapping.cheque_status_extension_url()), ['Used'])

    def test_status_never_goes_to_coverage_status(self):
        coverage = build_coverage()
        with mock.patch.dict(sys.modules, fake_cs_module([('ABC123', 'Cancel')])):
            CoverageConverter.build_csu_program(coverage, build_policy(build_program()))
        self.assertEqual(coverage.status, 'active')

    def test_cheque_not_in_registry(self):
        coverage = build_coverage()
        with mock.patch.dict(sys.modules, fake_cs_module([])):
            CoverageConverter.build_csu_program(coverage, build_policy(build_program()))
        self.assertEqual(coverage.identifier[0].value, 'ABC123')
        self.assertFalse(coverage.extension)

    def test_other_program_is_not_a_cheque(self):
        coverage = build_coverage()
        with mock.patch.dict(sys.modules, fake_cs_module([('ABC123', 'New')])):
            CoverageConverter.build_csu_program(coverage, build_policy(build_program(code='OTH')))
        self.assertFalse(coverage.identifier)
        self.assertFalse(coverage.extension)

    def test_cheque_program_detected_by_code_not_by_name(self):
        coverage = build_coverage()
        with mock.patch.dict(sys.modules, fake_cs_module([('ABC123', 'New')])):
            CoverageConverter.build_csu_program(
                coverage, build_policy(build_program(code='CCS', name='Autre programme')))
        self.assertEqual(coverage.identifier[0].value, 'ABC123')

    def test_instance_without_cs_module(self):
        coverage = build_coverage()
        with mock.patch.dict(sys.modules, {'cs': None, 'cs.models': None}):
            CoverageConverter.build_csu_program(coverage, build_policy(build_program()))
        self.assertEqual(coverage.identifier[0].value, 'ABC123')
        self.assertFalse(coverage.extension)

    def test_prefetched_status_avoids_registry_query(self):
        coverage = build_coverage()
        cs = fake_cs_module([('ABC123', 'New')])
        with mock.patch.dict(sys.modules, cs):
            CoverageConverter.build_csu_program(
                coverage, build_policy(build_program(), csu_cheque_status='Used'))
            cs['cs.models'].ChequeImportLine.objects.filter.assert_not_called()
        self.assertEqual(self._extension_values(coverage, ProgramMapping.cheque_status_extension_url()), ['Used'])

    def test_prefetched_none_means_not_in_registry(self):
        coverage = build_coverage()
        cs = fake_cs_module([('ABC123', 'New')])
        with mock.patch.dict(sys.modules, cs):
            CoverageConverter.build_csu_program(
                coverage, build_policy(build_program(), csu_cheque_status=None))
            cs['cs.models'].ChequeImportLine.objects.filter.assert_not_called()
        self.assertFalse(coverage.extension)


class CoveragePrefetchCsuTestCase(SimpleTestCase):

    def test_one_registry_query_for_the_page(self):
        cs = fake_cs_module([('AAA111', 'New'), ('BBB222', 'Used'), ('OTHER1', 'Cancel')])
        policies = [
            build_policy(build_program(), 'AAA111'),
            build_policy(build_program(), 'BBB222'),
            build_policy(build_program(), 'CCC333'),
            build_policy(build_program(code='OTH'), 'OTHER1'),
            build_policy(None, 'NOPRG1'),
        ]
        with mock.patch.dict(sys.modules, cs):
            CoverageRequestQuerySet.prefetch_csu_cheque_status(policies)
            self.assertEqual(cs['cs.models'].ChequeImportLine.objects.filter.call_count, 1)
        self.assertEqual(policies[0].csu_cheque_status, 'New')
        self.assertEqual(policies[1].csu_cheque_status, 'Used')
        self.assertIsNone(policies[2].csu_cheque_status)
        # not a cheque policy: nothing preloaded
        self.assertFalse(hasattr(policies[3], 'csu_cheque_status'))
        self.assertFalse(hasattr(policies[4], 'csu_cheque_status'))

    def test_no_query_without_cheque_policy(self):
        cs = fake_cs_module([])
        with mock.patch.dict(sys.modules, cs):
            CoverageRequestQuerySet.prefetch_csu_cheque_status([build_policy(None)])
            cs['cs.models'].ChequeImportLine.objects.filter.assert_not_called()

    def test_without_cs_module(self):
        policy = build_policy(build_program())
        with mock.patch.dict(sys.modules, {'cs': None, 'cs.models': None}):
            CoverageRequestQuerySet.prefetch_csu_cheque_status([policy])
        self.assertFalse(hasattr(policy, 'csu_cheque_status'))
