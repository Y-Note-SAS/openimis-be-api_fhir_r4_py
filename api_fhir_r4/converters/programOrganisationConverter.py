from django.utils.translation import gettext as _
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.organization import Organization
from fhir.resources.R4B.period import Period
from rest_framework.exceptions import MethodNotAllowed

from api_fhir_r4.converters import BaseFHIRConverter, ReferenceConverterMixin
from api_fhir_r4.mapping.programMapping import ProgramMapping


class ProgramOrganisationConverter(BaseFHIRConverter, ReferenceConverterMixin):
    """
    CSU specific converter.

    Exposes ``program.Program`` (a funder) as a read-only FHIR R4 Organization of type ``pay``.
    """

    @classmethod
    def to_fhir_obj(cls, imis_program, reference_type=ReferenceConverterMixin.UUID_REFERENCE_TYPE):
        fhir_organisation = Organization()
        cls.build_fhir_id(fhir_organisation, imis_program)
        cls.build_fhir_identifiers(fhir_organisation, imis_program)
        cls.build_fhir_type(fhir_organisation, imis_program)
        cls.build_fhir_name(fhir_organisation, imis_program)
        cls.build_fhir_validity_extension(fhir_organisation, imis_program)
        return fhir_organisation

    @classmethod
    def to_imis_obj(cls, fhir_organisation, audit_user_id):
        raise MethodNotAllowed('POST', detail=_('Programs are read-only, write operations are not supported.'))

    @classmethod
    def get_fhir_resource_type(cls):
        return Organization

    @classmethod
    def get_reference_obj_uuid(cls, imis_program):
        return ProgramMapping.to_fhir_id(imis_program)

    @classmethod
    def get_reference_obj_id(cls, imis_program):
        return ProgramMapping.to_fhir_id(imis_program)

    @classmethod
    def get_reference_obj_code(cls, imis_program):
        return ProgramMapping.to_fhir_id(imis_program)

    @classmethod
    def build_fhir_id(cls, fhir_organisation, imis_program):
        fhir_organisation.id = ProgramMapping.to_fhir_id(imis_program)

    @classmethod
    def build_fhir_identifiers(cls, fhir_organisation, imis_program):
        identifiers = []
        # Program.code is nullable: no identifier when it is not set.
        if imis_program.code:
            identifier = Identifier.construct()
            identifier.system = ProgramMapping.program_code_system()
            identifier.value = imis_program.code
            identifiers.append(identifier)
        fhir_organisation.identifier = identifiers

    @classmethod
    def build_fhir_type(cls, fhir_organisation, imis_program):
        fhir_organisation.type = [cls.build_codeable_concept(
            code=ProgramMapping.ORGANIZATION_TYPE,
            system=ProgramMapping.organization_type_system(),
            display=ProgramMapping.ORGANIZATION_TYPE_DISPLAY,
        )]

    @classmethod
    def build_fhir_name(cls, fhir_organisation, imis_program):
        fhir_organisation.name = imis_program.nameProgram

    @classmethod
    def build_fhir_validity_extension(cls, fhir_organisation, imis_program):
        # Organization has no period element, the validity is carried by an extension.
        if not imis_program.validityDateFrom and not imis_program.validityDateTo:
            return
        period = Period.construct()
        if imis_program.validityDateFrom:
            period.start = imis_program.validityDateFrom.isoformat()
        if imis_program.validityDateTo:
            period.end = imis_program.validityDateTo.isoformat()
        extension = Extension.construct()
        extension.url = ProgramMapping.validity_extension_url()
        extension.valuePeriod = period
        fhir_organisation.extension = [extension]
