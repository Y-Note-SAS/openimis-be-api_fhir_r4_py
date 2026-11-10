from api_fhir_r4.configurations import R4SubscriptionConfig
from core.apps import CoreConfig
from claim.apps import ClaimConfig
from insuree.apps import InsureeConfig
from location.apps import LocationConfig
from location.models import Location, HealthFacility
from policy.apps import PolicyConfig
from policyholder.apps import PolicyholderConfig
from product.apps import ProductConfig
from medical.apps import MedicalConfig
from invoice.apps import InvoiceConfig
from rest_framework import exceptions
from rest_framework.permissions import DjangoModelPermissions

# A right no role can hold: -1 is not a valid right identifier, so `has_perms([-1])`
# is False for everybody (superusers bypass it, as they do for any right).
#
# It says "this verb is not exposed". It is the opposite of [], which refuses
# nothing: `has_perms([])` returns True by construction, so an empty list OPENS the
# verb to every authenticated user. (Ported from the openIMIS reference,
# fix/setup-version-1.11.0.)
DENY = [-1]


def closed(perms, fallback=None):
    """A configured right list, or DENY (or ``fallback``) when the config leaves it empty.

    Several module configs ship ``[]`` for a query right; under ``has_perms([]) is True``
    that would open the FHIR verb to anyone logged in. Cameroon wants tight security, so
    an empty configuration closes the verb instead of opening it.
    """
    perms = list(perms or [])
    if perms:
        return perms
    return list(fallback) if fallback else DENY


class FHIRApiPermissions(DjangoModelPermissions):
    # Closed defaults: a subclass that forgets a verb refuses it instead of opening
    # it to everybody.
    permissions_get = DENY
    permissions_post = DENY
    permissions_put = DENY
    permissions_patch = DENY
    permissions_delete = DENY
    base_class = None

    def __init__(self):
        # Per-instance copy. `perms_map` is a class attribute on DRF's
        # DjangoModelPermissions: assigning into it mutated the one dict shared by every
        # permission class in the process, so whichever class was instantiated last
        # decided the rights of every view (a race under a threaded server).
        self.perms_map = dict(self.perms_map)
        self.perms_map['GET'] = self.permissions_get
        self.perms_map['POST'] = self.permissions_post
        self.perms_map['PUT'] = self.permissions_put
        self.perms_map['PATCH'] = self.permissions_patch
        self.perms_map['DELETE'] = self.permissions_delete

    def get_required_permissions(self, method, model_cls):
        if method not in self.perms_map:
            raise exceptions.MethodNotAllowed(method)

        return self.perms_map[method]


class FHIRApiClaimPermissions(FHIRApiPermissions):
    permissions_get = closed(ClaimConfig.gql_query_claims_perms)
    permissions_post = closed(ClaimConfig.gql_mutation_create_claims_perms)
    permissions_put = closed(ClaimConfig.gql_mutation_update_claims_perms)
    permissions_patch = closed(ClaimConfig.gql_mutation_update_claims_perms)
    permissions_delete = closed(ClaimConfig.gql_mutation_delete_claims_perms)


class FHIRApiCommunicationRequestPermissions(FHIRApiPermissions):
    # GET reads claims awaiting feedback: the claim query right (reference rights.py),
    # not a feedback *mutation* right as in v1.7.0.
    permissions_get = closed(ClaimConfig.gql_query_claims_perms)
    permissions_post = closed(ClaimConfig.gql_mutation_deliver_claim_feedback_perms)
    permissions_put = closed(ClaimConfig.gql_mutation_deliver_claim_feedback_perms)
    permissions_patch = closed(ClaimConfig.gql_mutation_deliver_claim_feedback_perms)
    permissions_delete = closed(ClaimConfig.gql_mutation_skip_claim_feedback_perms)


class FHIRApiPractitionerPermissions(FHIRApiPermissions):
    permissions_get = closed(CoreConfig.gql_query_claim_administrator_perms)
    permissions_post = closed(CoreConfig.gql_mutation_create_claim_administrator_perms)
    permissions_put = closed(CoreConfig.gql_mutation_update_claim_administrator_perms)
    permissions_patch = closed(CoreConfig.gql_mutation_update_claim_administrator_perms)
    permissions_delete = closed(CoreConfig.gql_mutation_delete_claim_administrator_perms)


class FHIRApiPractitionerOfficerPermissions(FHIRApiPermissions):
    permissions_get = closed(CoreConfig.gql_query_enrolment_officers_perms)
    permissions_post = closed(CoreConfig.gql_mutation_create_enrolment_officers_perms)
    permissions_put = closed(CoreConfig.gql_mutation_update_enrolment_officers_perms)
    permissions_patch = closed(CoreConfig.gql_mutation_update_enrolment_officers_perms)
    permissions_delete = closed(CoreConfig.gql_mutation_delete_enrolment_officers_perms)


class FHIRApiCoverageEligibilityRequestPermissions(FHIRApiPermissions):
    # POST is the only route: it *reads* eligibility, so it needs the eligibility right
    # (v1.7.0 left it at [], i.e. open to anyone logged in).
    permissions_get = closed(PolicyConfig.gql_query_eligibilities_perms)
    permissions_post = closed(PolicyConfig.gql_query_eligibilities_perms)
    permissions_put = DENY
    permissions_patch = DENY
    permissions_delete = DENY


class FHIRApiCoverageRequestPermissions(FHIRApiPermissions):
    # Contract and Coverage: POST/PUT/PATCH/DELETE were [] in v1.7.0, which opened
    # policy creation/update to anyone logged in (ContractSerializer.create calls
    # PolicyService.update_or_create, CoverageSerializer does a raw Policy create).
    permissions_get = closed(PolicyConfig.gql_query_policies_by_insuree_perms)
    permissions_post = closed(PolicyConfig.gql_mutation_create_policies_perms)
    permissions_put = closed(PolicyConfig.gql_mutation_edit_policies_perms)
    permissions_patch = closed(PolicyConfig.gql_mutation_edit_policies_perms)
    permissions_delete = closed(PolicyConfig.gql_mutation_delete_policies_perms)


class FHIRApiHFPermissions(FHIRApiPermissions):
    base_class = HealthFacility
    permissions_get = closed(LocationConfig.gql_query_health_facilities_perms)
    permissions_post = closed(LocationConfig.gql_mutation_create_health_facilities_perms)
    permissions_put = closed(LocationConfig.gql_mutation_edit_health_facilities_perms)
    permissions_patch = closed(LocationConfig.gql_mutation_edit_health_facilities_perms)
    permissions_delete = closed(LocationConfig.gql_mutation_delete_health_facilities_perms)


class FHIRApiLocationPermissions(FHIRApiPermissions):
    # v1.7.0 used the health facility rights for POST/PUT/DELETE of a Location.
    # GET keeps requiring the location query right: the reference opens it ([],
    # OMT-281), Cameroon keeps it closed.
    base_class = Location
    permissions_get = closed(LocationConfig.gql_query_locations_perms)
    permissions_post = closed(LocationConfig.gql_mutation_create_locations_perms)
    permissions_put = closed(LocationConfig.gql_mutation_edit_locations_perms)
    permissions_patch = closed(LocationConfig.gql_mutation_edit_locations_perms)
    permissions_delete = closed(LocationConfig.gql_mutation_delete_locations_perms)


class FHIRApiInsuranceOrganizationPermissions(FHIRApiPermissions):
    # Read-only resource built from module configuration; writes are stubs.
    permissions_get = closed(LocationConfig.gql_query_health_facilities_perms)


class FHIRApiInsureePermissions(FHIRApiPermissions):
    permissions_get = closed(InsureeConfig.gql_query_insurees_perms)
    permissions_post = closed(InsureeConfig.gql_mutation_create_insurees_perms)
    permissions_put = closed(InsureeConfig.gql_mutation_update_insurees_perms)
    permissions_patch = closed(InsureeConfig.gql_mutation_update_insurees_perms)
    permissions_delete = closed(InsureeConfig.gql_mutation_delete_insurees_perms)


class FHIRApiMedicationPermissions(FHIRApiPermissions):
    # GET keeps requiring the item query right (reference opens it, OMT-281).
    permissions_get = closed(MedicalConfig.gql_query_medical_items_perms)
    permissions_post = closed(MedicalConfig.gql_mutation_medical_items_add_perms)
    permissions_put = closed(MedicalConfig.gql_mutation_medical_items_update_perms)
    permissions_patch = closed(MedicalConfig.gql_mutation_medical_items_update_perms)
    permissions_delete = closed(MedicalConfig.gql_mutation_medical_items_delete_perms)


class FHIRApiConditionPermissions(FHIRApiPermissions):
    # Diagnoses: the medical config ships [] for the query right; coding a claim is
    # what needs them, so fall back to the claim query right rather than open them.
    permissions_get = closed(MedicalConfig.gql_query_diagnosis_perms,
                             fallback=ClaimConfig.gql_query_claims_perms)


class FHIRApiActivityDefinitionPermissions(FHIRApiPermissions):
    # GET keeps requiring the service query right (reference opens it, OMT-281).
    permissions_get = closed(MedicalConfig.gql_query_medical_services_perms)
    permissions_post = closed(MedicalConfig.gql_mutation_medical_services_add_perms)
    permissions_put = closed(MedicalConfig.gql_mutation_medical_services_update_perms)
    permissions_patch = closed(MedicalConfig.gql_mutation_medical_services_update_perms)
    permissions_delete = closed(MedicalConfig.gql_mutation_medical_services_delete_perms)


class FHIRApiHealthServicePermissions(FHIRApiPermissions):
    # Organization (health facility). v1.7.0 required "edit locations" to *read* a
    # health facility and used location rights for writes; the HF rights apply.
    # GET keeps requiring the HF query right (reference opens it, OMT-281).
    permissions_get = closed(LocationConfig.gql_query_health_facilities_perms)
    permissions_post = closed(LocationConfig.gql_mutation_create_health_facilities_perms)
    permissions_put = closed(LocationConfig.gql_mutation_edit_health_facilities_perms)
    permissions_patch = closed(LocationConfig.gql_mutation_edit_health_facilities_perms)
    permissions_delete = closed(LocationConfig.gql_mutation_delete_health_facilities_perms)


class FHIRApiGroupPermissions(FHIRApiPermissions):
    permissions_get = closed(InsureeConfig.gql_query_families_perms)
    permissions_post = closed(InsureeConfig.gql_mutation_create_families_perms)
    permissions_put = closed(InsureeConfig.gql_mutation_update_families_perms)
    permissions_patch = closed(InsureeConfig.gql_mutation_update_families_perms)
    permissions_delete = closed(InsureeConfig.gql_mutation_delete_families_perms)


class FHIRApiOrganizationPermissions(FHIRApiPermissions):
    permissions_get = closed(PolicyholderConfig.gql_query_policyholder_perms)
    permissions_post = closed(PolicyholderConfig.gql_mutation_create_policyholder_perms)
    permissions_put = closed(PolicyholderConfig.gql_mutation_update_policyholder_perms)
    permissions_patch = closed(PolicyholderConfig.gql_mutation_update_policyholder_perms)
    permissions_delete = closed(PolicyholderConfig.gql_mutation_delete_policyholder_perms)


class FHIRApiProductPermissions(FHIRApiPermissions):
    permissions_get = closed(ProductConfig.gql_query_products_perms)
    permissions_post = closed(ProductConfig.gql_mutation_products_add_perms)
    permissions_put = closed(ProductConfig.gql_mutation_products_edit_perms)
    permissions_patch = closed(ProductConfig.gql_mutation_products_edit_perms)
    permissions_delete = closed(ProductConfig.gql_mutation_products_delete_perms)


class FHIRApiInvoicePermissions(FHIRApiPermissions):
    permissions_get = closed(InvoiceConfig.gql_invoice_search_perms)
    permissions_post = closed(InvoiceConfig.gql_invoice_create_perms)
    permissions_put = closed(InvoiceConfig.gql_invoice_update_perms)
    permissions_patch = closed(InvoiceConfig.gql_invoice_update_perms)
    permissions_delete = closed(InvoiceConfig.gql_invoice_delete_perms)


class FHIRApiBillPermissions(FHIRApiPermissions):
    permissions_get = closed(InvoiceConfig.gql_bill_search_perms)
    permissions_post = closed(InvoiceConfig.gql_bill_create_perms)
    permissions_put = closed(InvoiceConfig.gql_bill_update_perms)
    permissions_patch = closed(InvoiceConfig.gql_bill_update_perms)
    permissions_delete = closed(InvoiceConfig.gql_bill_delete_perms)


class FHIRApiPaymentPermissions(FHIRApiPermissions):
    permissions_get = closed(InvoiceConfig.gql_invoice_payment_search_perms)
    permissions_post = closed(InvoiceConfig.gql_invoice_payment_create_perms)
    permissions_put = closed(InvoiceConfig.gql_invoice_payment_update_perms)
    permissions_patch = closed(InvoiceConfig.gql_invoice_payment_update_perms)
    permissions_delete = closed(InvoiceConfig.gql_invoice_payment_delete_perms)


class FHIRApiSubscriptionPermissions(FHIRApiPermissions):
    permissions_get = closed(R4SubscriptionConfig.get_fhir_sub_search_perms())
    permissions_post = closed(R4SubscriptionConfig.get_fhir_sub_create_perms())
    permissions_put = closed(R4SubscriptionConfig.get_fhir_sub_update_perms())
    permissions_patch = closed(R4SubscriptionConfig.get_fhir_sub_update_perms())
    permissions_delete = closed(R4SubscriptionConfig.get_fhir_sub_delete_perms())
