"""
FHIR R4 security parity tests: Cameroon (api_fhir_r4 v1.7.0) vs the openimis-dev-tools
reference (obenma fix/setup-version-1.11.0).

Every test asserts the REFERENCE behaviour (or the property the reference is meant to
guarantee): a FAILURE is a security gap in the Cameroon deployment.
Docstring tags:
  [REF <file>::<test>]  ported from the reference test suite
  [NEW]                 no equivalent in the reference (reference may share the gap)

Rights are checked over HTTP (JWT bearer, as a real client would). Row scope is checked
on the queryset each viewset serves for the authenticated user (the same queryset list
and retrieve use), which keeps the fixtures small: the user is granted district D1 only,
every "*2" object lives in district D2 and must never be served.
"""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APITestCase

from api_fhir_r4.configurations import GeneralConfiguration, R4SubscriptionConfig
from api_fhir_r4 import permissions as fhir_perms
from claim.apps import ClaimConfig
from core.apps import CoreConfig
from core.test_helpers import (
    create_right_only_user,
    create_security_tree,
    get_test_token,
    perm_ids,
)
from insuree.apps import InsureeConfig
from location.apps import LocationConfig
from policy.apps import PolicyConfig

BASE_URL = GeneralConfiguration.get_base_url()


def _bearer(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {get_test_token(user)}"}


class _HttpBase(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        # a 500 must come back as a response, not abort the test: the permission layer
        # is what is asserted, not the serializer behind it
        self.client.raise_request_exception = False

    def _call(self, method, path, user, data=None, params=None):
        fn = getattr(self.client, method)
        kwargs = {"format": "json", **_bearer(user)}
        if data is not None:
            kwargs["data"] = data
        if params is not None:
            kwargs["data"] = params
        return fn(BASE_URL + path, **kwargs)


# ---------------------------------------------------------------------------------------
# 1. API rights enforcement (HTTP)
# ---------------------------------------------------------------------------------------

class ContractCreateRightTests(_HttpBase):
    """POST /Contract creates a real policy: it must require the create-policy right."""

    def test_post_forbidden_without_create_policy_right(self):
        """[REF test_api_rights_enforcement.py::ContractCreatePermissionAPITests.test_post_forbidden_without_create_policy_right]"""
        user = create_right_only_user("spf_contract_none", [])
        response = self._call("post", "Contract/", user, data={"resourceType": "Contract"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                         f"Contract POST reached the serializer: {response.status_code}")

    def test_post_passes_permission_layer_with_create_policy_right(self):
        """[REF test_api_rights_enforcement.py::ContractCreatePermissionAPITests.test_post_allowed_with_create_policy_right]
        (adapted: only asserts the permission layer lets it through)"""
        user = create_right_only_user(
            "spf_contract_ok", perm_ids(PolicyConfig.gql_mutation_create_policies_perms))
        response = self._call("post", "Contract/", user, data={"resourceType": "Contract"})
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CoverageEligibilityRequestRightTests(_HttpBase):
    """POST /CoverageEligibilityRequest performs the eligibility lookup on any CHF id."""

    def test_post_forbidden_without_eligibility_right(self):
        """[REF test_api_rights_enforcement.py::CoverageEligibilityRequestPermissionAPITests.test_post_forbidden_without_eligibility_right]"""
        user = create_right_only_user("spf_elig_none", [])
        response = self._call("post", "CoverageEligibilityRequest/", user,
                              data={"resourceType": "CoverageEligibilityRequest"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                         f"eligibility POST reached the serializer: {response.status_code}")

    def test_post_passes_permission_layer_with_eligibility_right(self):
        """[REF test_api_rights_enforcement.py::CoverageEligibilityRequestPermissionAPITests.test_post_allowed_with_eligibility_right]"""
        user = create_right_only_user(
            "spf_elig_ok", perm_ids(PolicyConfig.gql_query_eligibilities_perms))
        response = self._call("post", "CoverageEligibilityRequest/", user,
                              data={"resourceType": "CoverageEligibilityRequest"})
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CoverageWriteRightTests(_HttpBase):
    """Coverage POST/PUT must require policy write rights (reference: POLICY_ADD/CHANGE)."""

    def test_post_forbidden_without_policy_right(self):
        """[NEW] reference closes it with POLICY_ADD (permissions.py:153-158)"""
        user = create_right_only_user("spf_cov_post", [])
        response = self._call("post", "Coverage/", user, data={"resourceType": "Coverage"})
        # 405 would also be acceptable (route not exposed); anything else means open
        self.assertIn(response.status_code,
                      (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED),
                      f"Coverage POST reached the serializer: {response.status_code}")

    def test_put_forbidden_without_policy_right(self):
        """[NEW] UpdateModelMixin is mounted with permissions_put = [] (any authenticated user)"""
        user = create_right_only_user("spf_cov_put", [])
        response = self._call("put", "Coverage/00000000-0000-0000-0000-000000000000/", user,
                              data={"resourceType": "Coverage"})
        self.assertIn(response.status_code,
                      (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED),
                      f"Coverage PUT passed the permission layer: {response.status_code}")


class EmptyRoleTests(_HttpBase):

    def test_empty_role_is_forbidden_on_claim(self):
        """[REF test_api_authorization.py::test_post_should_raise_forbidden] empty role -> 403 on GET Claim"""
        user = create_right_only_user("spf_empty_role", [])
        response = self._call("get", "Claim/", user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_is_unauthorized_on_patient(self):
        """[REF test_api_authorization.py] no token -> 401"""
        response = self.client.get(BASE_URL + "Patient/", format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PractitionerRightTests(_HttpBase):

    def test_get_ca_forbidden_without_any_practitioner_right(self):
        """[REF test_api_rights_enforcement.py::PractitionerClaimAdminPermissionAPITests.test_get_ca_forbidden_without_any_practitioner_right]"""
        user = create_right_only_user("spf_prac_none", [])
        response = self._call("get", "Practitioner/", user, params={"resourceType": "ca"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_ca_allowed_with_claim_administrator_right(self):
        """[REF test_api_rights_enforcement.py::PractitionerClaimAdminPermissionAPITests.test_get_ca_allowed_with_claim_administrator_right]"""
        user = create_right_only_user(
            "spf_prac_ca", perm_ids(CoreConfig.gql_query_claim_administrator_perms))
        response = self._call("get", "Practitioner/", user, params={"resourceType": "ca"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content[:300])

    def test_get_eo_forbidden_without_any_practitioner_right(self):
        """[REF test_api_rights_enforcement.py::PractitionerEnrolmentOfficerPermissionAPITests.test_get_eo_forbidden_without_any_practitioner_right]"""
        user = create_right_only_user("spf_prac_none2", [])
        response = self._call("get", "Practitioner/", user, params={"resourceType": "eo"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_eo_allowed_with_enrolment_officer_right(self):
        """[REF test_api_rights_enforcement.py::PractitionerEnrolmentOfficerPermissionAPITests.test_get_eo_allowed_with_enrolment_officer_right]"""
        user = create_right_only_user(
            "spf_prac_eo", perm_ids(CoreConfig.gql_query_enrolment_officers_perms))
        response = self._call("get", "Practitioner/", user, params={"resourceType": "eo"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content[:300])


    def test_get_ca_allowed_with_claim_right(self):
        """[CSU dev-csu a7a9547] claim apps read claim administrators with the claim query right"""
        from claim.apps import ClaimConfig
        user = create_right_only_user("spf_prac_claim", perm_ids(ClaimConfig.gql_query_claims_perms))
        response = self._call("get", "Practitioner/", user, params={"resourceType": "ca"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content[:300])


class OrganizationCodeSystemRightTests(_HttpBase):
    """[NEW] the organization-* code systems only require authentication (reference: same)."""

    PATHS = (
        "CodeSystem/organization-hf-legal-form/",
        "CodeSystem/organization-hf-level/",
        "CodeSystem/organization-ph-legal-form/",
        "CodeSystem/organization-ph-activity/",
    )

    def test_organization_code_systems_require_a_right(self):
        """[NEW] a user without any right must get 403 (other code systems check a right in list())"""
        user = create_right_only_user("spf_cs_none", [])
        for path in self.PATHS:
            with self.subTest(path=path):
                response = self._call("get", path, user)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                                 f"{path} -> {response.status_code}")


# ---------------------------------------------------------------------------------------
# 2. Permission-class mechanics (unit)
# ---------------------------------------------------------------------------------------

class OperationOutcomeFromApiExceptionTests(TestCase):
    """[NEW] a DRF exception detail that is not a string (ValidationError) builds an outcome"""

    def _text(self, exc):
        from api_fhir_r4.converters import OperationOutcomeConverter
        return OperationOutcomeConverter.to_fhir_obj(exc).dict()["issue"][0]["details"]["text"]

    def test_dict_detail(self):
        from rest_framework.exceptions import ValidationError
        self.assertEqual("refDate: bad format", self._text(ValidationError({"refDate": "bad format"})))

    def test_list_detail(self):
        from rest_framework.exceptions import ValidationError
        self.assertEqual("first; second", self._text(ValidationError(["first", "second"])))

    def test_string_detail_unchanged(self):
        from rest_framework.exceptions import PermissionDenied
        self.assertEqual("nope", self._text(PermissionDenied("nope")))


class PermsMapIsolationTests(TestCase):

    def test_perms_map_is_not_the_drf_class_attribute(self):
        """[REF test_permissions_alignment.py::test_perms_map_is_not_the_drf_class_attribute]"""
        insuree = fhir_perms.FHIRApiInsureePermissions()
        self.assertIsNot(insuree.perms_map, DjangoModelPermissions.perms_map)

    def test_perms_map_is_not_shared_between_permission_classes(self):
        """[REF test_permissions_alignment.py::test_perms_map_is_not_shared_between_permission_classes]"""
        insuree = fhir_perms.FHIRApiInsureePermissions()
        before = list(insuree.perms_map["GET"])
        fhir_perms.FHIRApiPermissions()  # every verb [] in v1.7.0
        self.assertEqual(insuree.perms_map["GET"], before,
                         "instantiating another permission class altered this one")

    def test_an_empty_resource_does_not_leak_into_another(self):
        """[REF test_permissions_alignment.py::test_an_empty_resource_does_not_leak_into_another]
        (adapted: the reference uses Location GET=[]; here the base class is the empty one,
        as instantiated by every multi-serializer request)"""
        insuree = fhir_perms.FHIRApiInsureePermissions()
        fhir_perms.FHIRApiCoverageRequestPermissions()  # POST = []
        claim = fhir_perms.FHIRApiClaimPermissions()
        fhir_perms.FHIRApiPermissions()
        from insuree.models import Insuree
        from claim.models import Claim
        self.assertTrue(insuree.get_required_permissions("GET", Insuree),
                        "Insuree GET requirement was blanked by another class")
        self.assertTrue(claim.get_required_permissions("POST", Claim),
                        "Claim POST requirement was blanked by another class")


class DenySentinelTests(TestCase):

    def test_empty_list_grants_everyone(self):
        """[REF test_permissions_alignment.py::DenySentinelTestCase.test_deny_is_refused_and_empty_is_granted]
        (Cameroon has no DENY sentinel; this pins the hazard: [] == open)"""
        user = create_right_only_user("spf_deny_probe", perm_ids(CoreConfig.gql_query_users_perms))
        self.assertTrue(user.has_perms([]), "[] grants everyone by construction")
        self.assertFalse(user.has_perms([-1]), "an unknown right id must refuse")

    def test_base_class_defaults_are_closed(self):
        """[REF test_permissions_alignment.py::DenySentinelTestCase.test_base_class_defaults_are_closed]"""
        for verb in ("get", "post", "put", "patch", "delete"):
            with self.subTest(verb=verb):
                self.assertTrue(getattr(fhir_perms.FHIRApiPermissions, f"permissions_{verb}"),
                                f"FHIRApiPermissions.permissions_{verb} is [] (open)")

    def test_no_write_verb_is_open(self):
        """[REF test_permissions_alignment.py::DenySentinelTestCase] (generalised) no concrete
        permission class may leave a write verb at [] - reference uses DENY instead"""
        open_writes = []
        for name in dir(fhir_perms):
            cls = getattr(fhir_perms, name)
            if (isinstance(cls, type) and issubclass(cls, fhir_perms.FHIRApiPermissions)
                    and cls is not fhir_perms.FHIRApiPermissions):
                for verb in ("post", "put", "patch", "delete"):
                    if getattr(cls, f"permissions_{verb}") == []:
                        open_writes.append(f"{name}.{verb}")
        self.assertEqual([], open_writes, f"write verbs open to any authenticated user: {open_writes}")

    def test_location_writes_use_location_rights(self):
        """[NEW] Location POST/PUT/DELETE use the health-facility rights in v1.7.0;
        reference uses LOCATION_* (permissions.py:161-167)"""
        p = fhir_perms.FHIRApiLocationPermissions
        self.assertEqual(list(p.permissions_post), list(LocationConfig.gql_mutation_create_locations_perms))
        self.assertEqual(list(p.permissions_delete), list(LocationConfig.gql_mutation_delete_locations_perms))


# ---------------------------------------------------------------------------------------
# 3. Row scope: what each viewset serves to a D1-only user
# ---------------------------------------------------------------------------------------

class FhirRowScopeTests(TestCase):
    """[NEW] (reference has no FHIR scoping test; reference viewsets call Model.get_queryset)"""

    @classmethod
    def setUpTestData(cls):
        from insuree.test_helpers import create_test_insuree
        cls.t = create_security_tree("SPF")
        rights = (
            perm_ids(InsureeConfig.gql_query_insurees_perms)
            + perm_ids(InsureeConfig.gql_query_families_perms)
            + perm_ids(ClaimConfig.gql_query_claims_perms)
            + perm_ids(PolicyConfig.gql_query_policies_by_insuree_perms)
            + perm_ids(LocationConfig.gql_query_health_facilities_perms)
            + perm_ids(CoreConfig.gql_query_claim_administrator_perms)
        )
        cls.user = create_right_only_user("spf_scope_d1", rights, [cls.t.d1.id])
        cls.other_user = create_right_only_user("spf_scope_d2", rights, [cls.t.d2.id])
        cls.ins1 = create_test_insuree(
            custom_props={"chf_id": "SPF000001", "current_village": cls.t.v1},
            family_custom_props={"location": cls.t.v1})
        cls.ins2 = create_test_insuree(
            custom_props={"chf_id": "SPF000002", "current_village": cls.t.v2},
            family_custom_props={"location": cls.t.v2})
        # an insuree living in D2 whose current village was never captured
        cls.ins2_nullvillage = create_test_insuree(
            custom_props={"chf_id": "SPF000003", "current_village": cls.t.v2},
            family_custom_props={"location": cls.t.v2})
        # the helper copies a None village onto the family: clear the village afterwards
        type(cls.ins2_nullvillage).objects.filter(pk=cls.ins2_nullvillage.pk).update(current_village=None)

    def setUp(self):
        cache.clear()

    def _served(self, viewset_cls, user=None, method=None, params=None):
        view = viewset_cls()
        view.format_kwarg = None
        view.kwargs = {}
        view.action = "list"
        request = Request(APIRequestFactory().get("/", params or {}))
        request.user = user or self.user
        view.request = request
        qs = getattr(view, method)() if method else view.get_queryset()
        return qs

    # -- Patient / Group ------------------------------------------------------------
    def test_patient_hides_other_district(self):
        """[NEW] Patient list/retrieve must not serve a D2 insuree"""
        from api_fhir_r4.views.fhir.insuree import InsureeViewSet
        ids = set(self._served(InsureeViewSet).values_list("id", flat=True))
        self.assertIn(self.ins1.id, ids, "sanity: own-district insuree visible")
        self.assertNotIn(self.ins2.id, ids)

    def test_patient_hides_other_district_insuree_without_current_village(self):
        """[NEW] insuree with current_village NULL, family in D2 (location filter keeps NULLs)"""
        from api_fhir_r4.views.fhir.insuree import InsureeViewSet
        ids = set(self._served(InsureeViewSet).values_list("id", flat=True))
        self.assertNotIn(self.ins2_nullvillage.id, ids)

    def test_group_hides_other_district(self):
        """[NEW] reference group.py:41 uses Family.get_queryset; v1.7.0 serves Family.objects.all()"""
        from api_fhir_r4.views.fhir.group import GroupViewSet
        ids = set(self._served(GroupViewSet).values_list("id", flat=True))
        self.assertNotIn(self.ins2.family_id, ids)

    # -- Claim / Communication -------------------------------------------------------
    def _claim_in(self, hf, insuree):
        from claim.test_helpers import create_test_claim
        from medical.models import Diagnosis
        from program.models import Program
        from program.test_helpers import create_test_program
        program = Program.objects.filter(code="SPFPRG").first() or create_test_program(code="SPFPRG")
        return create_test_claim({
            "program": program,
            "health_facility_id": hf.id,
            "insuree_id": insuree.id,
            "icd_id": Diagnosis.objects.filter(validity_to__isnull=True).first().id,
        })

    def test_claim_hides_other_district(self):
        """[NEW] Claim.get_queryset is used (same as reference)"""
        from api_fhir_r4.views.fhir.claim import ClaimViewSet
        claim1 = self._claim_in(self.t.hf1, self.ins1)
        claim2 = self._claim_in(self.t.hf2, self.ins2)
        ids = set(self._served(ClaimViewSet).values_list("id", flat=True))
        self.assertIn(claim1.id, ids, "sanity: own-district claim visible")
        self.assertNotIn(claim2.id, ids)

    def _listed_claim_ids(self, patient):
        """the claims the list hands to the paginator for ?patient= (the serializer is not
        under test: rendering a claim needs fixtures far beyond the scope check)"""
        from unittest import mock
        from rest_framework.test import APIClient
        from api_fhir_r4.views.fhir.claim import ClaimViewSet
        listed = []

        def paginate(view, queryset):
            listed.extend(queryset.values_list("id", flat=True))
            return []
        from rest_framework.response import Response
        client = APIClient(raise_request_exception=False)
        with mock.patch.object(ClaimViewSet, "paginate_queryset", paginate), \
                mock.patch.object(ClaimViewSet, "get_paginated_response", lambda view, data: Response([])):
            response = client.get(BASE_URL + "Claim/", {"patient": str(patient)}, **_bearer(self.user))
        self.assertEqual(status.HTTP_200_OK, response.status_code, response.content)
        return set(listed)

    def test_claim_list_patient_filter_within_scope(self):
        """[NEW] ?patient= on the claim list returns the claims of that insuree only"""
        from api_fhir_r4.views.fhir.claim import ClaimViewSet
        claim1 = self._claim_in(self.t.hf1, self.ins1)
        other = self._claim_in(self.t.hf1, self.ins2)
        self.assertEqual({claim1.id}, self._listed_claim_ids(self.ins1.uuid))
        self.assertIn(other.id, set(self._served(ClaimViewSet).values_list("id", flat=True)),
                      "sanity: the D2 insuree's claim in D1 is visible in the plain list")

    def test_claim_list_patient_out_of_scope_like_unknown(self):
        """[NEW] claim.py: the patient is looked up within the user's scope (Insuree.get_queryset).
        A D2 insuree treated in D1 has a claim the user sees, but filtering on that patient must
        not confirm they exist: the same empty list as an unknown uuid, not a 500"""
        self._claim_in(self.t.hf1, self.ins2)
        self.assertEqual(set(), self._listed_claim_ids(self.ins2.uuid))
        self.assertEqual(set(), self._listed_claim_ids("00000000-0000-0000-0000-000000000000"))

    def test_claim_list_patient_not_a_uuid(self):
        """[NEW] a malformed patient is a client error (400 OperationOutcome), not a 500"""
        from rest_framework.test import APIClient
        response = APIClient(raise_request_exception=False).get(
            BASE_URL + "Claim/", {"patient": "not-a-uuid"}, **_bearer(self.user))
        self.assertEqual(status.HTTP_400_BAD_REQUEST, response.status_code, response.content)
        self.assertEqual("OperationOutcome", response.json()["resourceType"])
        self.assertIn("patient", response.json()["issue"][0]["details"]["text"])

    def test_communication_hides_other_district_feedback(self):
        """[NEW] reference communication.py:42 uses Feedback.get_queryset; v1.7.0 serves all feedbacks"""
        from api_fhir_r4.views.fhir.communication import CommunicationViewSet
        from claim.models import Feedback
        claim2 = self._claim_in(self.t.hf2, self.ins2)
        fb = Feedback.objects.create(claim=claim2, audit_user_id=-1,
                                     validity_from=timezone.now(), feedback_date=timezone.now())
        ids = set(self._served(CommunicationViewSet).values_list("id", flat=True))
        self.assertNotIn(fb.id, ids)

    # -- Contract / Coverage -----------------------------------------------------------
    def _policy_in_d2(self):
        from policy.test_helpers import create_test_policy
        from product.test_helpers import create_test_product
        product = create_test_product("SPFPR")
        return create_test_policy(product, self.ins2)

    def test_contract_and_coverage_hide_other_district_policy(self):
        """[NEW] Policy.get_queryset is used (same as reference)"""
        from api_fhir_r4.views.fhir.contract import ContractViewSet
        from api_fhir_r4.views.fhir.coverage_request import CoverageRequestQuerySet
        policy2 = self._policy_in_d2()
        for vs in (ContractViewSet, CoverageRequestQuerySet):
            with self.subTest(viewset=vs.__name__):
                ids = set(self._served(vs).values_list("id", flat=True))
                self.assertNotIn(policy2.id, ids)

    # -- Organization / Practitioner --------------------------------------------------
    def test_organization_hides_other_district_hf(self):
        """[NEW] reference organisation.py:255 uses HealthFacility.get_queryset; v1.7.0 serves all"""
        from api_fhir_r4.views.fhir.organisation import OrganisationViewSet
        codes = set(self._served(OrganisationViewSet, method="_hf_queryset")
                    .values_list("code", flat=True))
        self.assertNotIn(self.t.hf2.code, codes)

    def test_practitioner_hides_other_district_claim_admin(self):
        """[NEW] reference practitioner.py:95 uses ClaimAdmin.get_queryset; v1.7.0 serves all"""
        from api_fhir_r4.views.fhir.practitioner import PractitionerViewSet
        from claim.test_helpers import create_test_claim_admin
        ca2 = create_test_claim_admin({"code": "SPFCA2", "health_facility_id": self.t.hf2.id})
        ids = set(self._served(PractitionerViewSet, method="_ca_queryset")
                  .values_list("id", flat=True))
        self.assertNotIn(ca2.id, ids)

    def test_practitioner_role_hides_other_district_claim_admin(self):
        """[NEW] same as Practitioner for PractitionerRole"""
        from api_fhir_r4.views.fhir.practitioner_role import PractitionerRoleViewSet
        from claim.test_helpers import create_test_claim_admin
        ca2 = create_test_claim_admin({"code": "SPFCA3", "health_facility_id": self.t.hf2.id})
        ids = set(self._served(PractitionerRoleViewSet, method="_ca_queryset")
                  .values_list("id", flat=True))
        self.assertNotIn(ca2.id, ids)

    # -- Invoice / PaymentNotice -------------------------------------------------------
    def _invoice_on_d2_policy(self):
        try:
            from invoice.tests.helpers import create_test_invoice
            return create_test_invoice(subject=self._policy_in_d2(), thirdparty=self.ins2,
                                       code="SPFINV2")
        except Exception as exc:  # heavy fixture chain (contract/policyholder)
            self.skipTest(f"invoice fixture unavailable: {exc!r}")

    def test_invoice_hides_other_district(self):
        """[NEW] reference invoice.py:94 uses Invoice.get_queryset (GenericScope on subject);
        v1.7.0 serves Invoice.objects (and Cameroon invoice 1.7.0 get_queryset is a no-op)"""
        from api_fhir_r4.views.fhir.invoice import InvoiceViewSet
        inv2 = self._invoice_on_d2_policy()
        ids = set(self._served(InvoiceViewSet, method="_invoice_queryset")
                  .values_list("id", flat=True))
        self.assertNotIn(inv2.id, ids)

    def test_payment_notice_hides_other_district(self):
        """[NEW] reference payment_notice.py:41 uses PaymentInvoice.get_queryset"""
        from api_fhir_r4.views.fhir.payment_notice import PaymentNoticeViewSet
        inv2 = self._invoice_on_d2_policy()
        try:
            from invoice.tests.helpers.payment_invoice_helpers import \
                create_test_payment_invoice_with_details
            payment = create_test_payment_invoice_with_details(invoice=inv2)
        except Exception as exc:
            self.skipTest(f"payment fixture unavailable: {exc!r}")
        ids = set(self._served(PaymentNoticeViewSet).values_list("id", flat=True))
        self.assertNotIn(payment.id, ids)

    # -- Subscription -----------------------------------------------------------------
    def test_subscription_list_hides_other_users_subscriptions(self):
        """[NEW] list serves every user's subscriptions (reference: same gap, owner checked on delete only)"""
        from api_fhir_r4.models import Subscription
        from api_fhir_r4.views.fhir.subscription import SubscriptionViewSet
        sub = Subscription(status=1, channel=0, endpoint="https://example.invalid/hook",
                           criteria={"resource": "Patient"},
                           expiring=timezone.now() + timedelta(days=30))
        sub.save(username=self.other_user.username)
        ids = set(self._served(SubscriptionViewSet).values_list("id", flat=True))
        self.assertNotIn(sub.id, ids)
